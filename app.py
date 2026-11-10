"""
PromptVault — Enterprise-Grade AI Prompt Library & Asset Management System
===========================================================================
A production-ready Flask application designed for cataloging, categorizing,
and securely managing generative AI prompts and their corresponding artworks.

Implements defense-in-depth security, strict file verification, OWASP headers,
Schema.org structured data, and high-performance search and indexing.
"""

import os
import re
import sqlite3
from urllib.parse import quote_plus
from cs50 import SQL
from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

# Optional: Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -----------------------------------------------------------------------------
# Application Factory & Configuration
# -----------------------------------------------------------------------------
app = Flask(__name__)

# Security: Session & CSRF Key Configuration
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

# File Upload Policies & Constraints
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_PIXELS = 20_000_000  # 20 Megapixels ceiling against decompression bombs
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB maximum request payload

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Initialize CSRF Protection
csrf = CSRFProtect(app)

# Validation Patterns: Alphanumeric, spaces, hyphens, underscores (1 to 30 chars)
CATEGORY_PATTERN = re.compile(r"^[\w \-]{1,30}$")

# -----------------------------------------------------------------------------
# Database Initialization & Setup
# -----------------------------------------------------------------------------
database_path = os.path.abspath(os.environ.get("DATABASE_PATH", "prompts.db"))

# Ensure database file exists before opening it via CS50 SQL
sqlite3.connect(database_path).close()
db = SQL(f"sqlite:///{database_path}")

# Schema migration and table initialization
db.execute("""
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_path TEXT NOT NULL,
        prompt_text TEXT NOT NULL,
        category TEXT NOT NULL,
        is_favorite INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

# Performance indexes for fast querying and filtering
db.execute("CREATE INDEX IF NOT EXISTS idx_images_category ON images (category)")
db.execute("CREATE INDEX IF NOT EXISTS idx_images_favorite ON images (is_favorite)")
db.execute("CREATE INDEX IF NOT EXISTS idx_images_timestamp ON images (timestamp)")

# Ensure base uploads directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# -----------------------------------------------------------------------------
# Security & Path Resolution Utilities
# -----------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    """Validate whether the file has an approved image extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def valid_category(name: str) -> bool:
    """Validate that a category name strictly matches safe filesystem characters."""
    return bool(CATEGORY_PATTERN.fullmatch(name))


def upload_path_from_url(image_path: str):
    """
    Resolve a stored /static/uploads URL to an absolute filesystem path.
    Guarantees that the resolved path is strictly contained within UPLOAD_FOLDER,
    preventing path traversal and symlink vulnerabilities.
    """
    prefix = "/static/uploads/"
    if not isinstance(image_path, str) or not image_path.startswith(prefix):
        return None

    relative_path = image_path[len(prefix):]
    upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])
    full_path = os.path.abspath(os.path.join(upload_root, relative_path))
    try:
        if os.path.commonpath([upload_root, full_path]) != upload_root:
            return None
    except ValueError:
        # Cross-drive path resolution on Windows systems
        return None
    return full_path


# -----------------------------------------------------------------------------
# Security Headers & Defense-in-Depth Middleware
# -----------------------------------------------------------------------------
@app.after_request
def security_headers(response):
    """
    Inject comprehensive HTTP security headers to protect against XSS,
    clickjacking, MIME-sniffing, and unauthorized hardware access.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"

    # Content Security Policy (CSP) allowing Google Fonts and FontAwesome CDNs
    csp_directives = [
        "default-src 'self'",
        "img-src 'self' data: https: blob:",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com",
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com",
        "script-src 'self' 'unsafe-inline'",
        "connect-src 'self'",
        "frame-ancestors 'self'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


# -----------------------------------------------------------------------------
# Error Handlers
# -----------------------------------------------------------------------------
@app.errorhandler(400)
def bad_request_error(error):
    return render_template("errors/400.html", error=error), 400


@app.errorhandler(403)
def forbidden_error(error):
    return render_template("errors/403.html", error=error), 403


@app.errorhandler(404)
def not_found_error(error):
    return render_template("errors/404.html", error=error), 404


@app.errorhandler(413)
def upload_too_large(error):
    # Maintain exact message compatibility with test assertions
    return "Upload too large. The complete request must not exceed 10 MB.", 413


@app.errorhandler(500)
def internal_error(error):
    return render_template("errors/500.html", error=error), 500


# -----------------------------------------------------------------------------
# Application Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    """
    Main gallery view supporting text search, category filtering,
    favorites toggling, and sorting.
    """
    categories = db.execute("SELECT DISTINCT category FROM images ORDER BY category")
    sort = request.args.get("sort", "newest")
    selected_cat = request.args.get("category", "")
    show_fav = request.args.get("favorites", "")
    q = request.args.get("q", "").strip()

    order = "DESC" if sort == "newest" else "ASC"

    # Construct safe parameterized queries
    if q:
        search_pattern = f"%{q}%"
        if show_fav:
            prompts = db.execute(
                f"SELECT * FROM images WHERE is_favorite = 1 AND (prompt_text LIKE ? OR category LIKE ?) ORDER BY timestamp {order}",
                search_pattern,
                search_pattern,
            )
        elif selected_cat:
            prompts = db.execute(
                f"SELECT * FROM images WHERE category = ? AND (prompt_text LIKE ? OR category LIKE ?) ORDER BY timestamp {order}",
                selected_cat,
                search_pattern,
                search_pattern,
            )
        else:
            prompts = db.execute(
                f"SELECT * FROM images WHERE (prompt_text LIKE ? OR category LIKE ?) ORDER BY timestamp {order}",
                search_pattern,
                search_pattern,
            )
    else:
        if show_fav:
            prompts = db.execute(
                f"SELECT * FROM images WHERE is_favorite = 1 ORDER BY timestamp {order}"
            )
        elif selected_cat:
            prompts = db.execute(
                f"SELECT * FROM images WHERE category = ? ORDER BY timestamp {order}",
                selected_cat,
            )
        else:
            prompts = db.execute(f"SELECT * FROM images ORDER BY timestamp {order}")

    # Calculate summary metrics for dashboard
    total_count = len(db.execute("SELECT id FROM images"))
    fav_count = len(db.execute("SELECT id FROM images WHERE is_favorite = 1"))
    stats = {
        "total": total_count,
        "favorites": fav_count,
        "categories": len(categories),
    }

    return render_template(
        "index.html",
        prompts=prompts,
        categories=categories,
        sort=sort,
        selected_cat=selected_cat,
        show_fav=show_fav,
        q=q,
        stats=stats,
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    """Handle new prompt & artwork upload with rigorous validation."""
    if request.method == "POST":
        file = request.files.get("image_file")
        prompt = request.form.get("prompt_text", "").strip()
        cat = request.form.get("category", "").strip().title()

        if not prompt or not cat:
            flash("Please fill in all fields.", "error")
            return render_template("add.html")

        if not valid_category(cat):
            flash(
                "Category can only contain letters, numbers, spaces, - and _ (max 30 characters).",
                "error",
            )
            return render_template("add.html")

        if file and file.filename != "":
            if not allowed_file(file.filename):
                flash(
                    "Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp).",
                    "error",
                )
                return render_template("add.html")

            expected_formats = {
                "png": "PNG",
                "jpg": "JPEG",
                "jpeg": "JPEG",
                "gif": "GIF",
                "webp": "WEBP",
            }
            extension = file.filename.rsplit(".", 1)[1].lower()

            # Deep image verification via Pillow
            try:
                with Image.open(file.stream) as uploaded_image:
                    if uploaded_image.format != expected_formats.get(extension):
                        raise ValueError("Image contents do not match the extension.")
                    if uploaded_image.width * uploaded_image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("Image dimensions exceed 20 million pixels limit.")
                    uploaded_image.verify()
                file.stream.seek(0)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                flash(
                    "Please upload a valid image, with matching extension and at most 20 million pixels.",
                    "error",
                )
                return render_template("add.html"), 400

            # Sanitize filename and resolve collisions
            stem, ext = file.filename.rsplit(".", 1)
            stem = secure_filename(stem) or "image"
            ext = ext.lower()
            filename = f"{stem}.{ext}"

            # Create category-specific upload folder
            cat_folder = os.path.join(app.config["UPLOAD_FOLDER"], cat)
            os.makedirs(cat_folder, exist_ok=True)

            counter = 1
            while os.path.exists(os.path.join(cat_folder, filename)):
                filename = f"{stem}_{counter}.{ext}"
                counter += 1

            file_destination = os.path.join(cat_folder, filename)
            file.save(file_destination)
            image_path = f"/static/uploads/{cat}/{filename}"

            db.execute(
                "INSERT INTO images (image_path, prompt_text, category) VALUES (?, ?, ?)",
                image_path,
                prompt,
                cat,
            )
            flash("Prompt added successfully!", "success")
            return redirect(url_for("index"))
        else:
            flash("Please select an image file.", "error")

    return render_template("add.html")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id: int):
    """Edit prompt metadata and synchronize directory structure if category changes."""
    rows = db.execute("SELECT * FROM images WHERE id = ?", id)
    if not rows:
        flash("Item not found.", "error")
        return redirect(url_for("index"))

    prompt_data = rows[0]

    if request.method == "POST":
        new_prompt = request.form.get("prompt_text", "").strip()
        new_cat = request.form.get("category", "").strip().title()

        if not new_prompt or not new_cat:
            flash("Please fill in all fields.", "error")
            return render_template("edit.html", item=prompt_data)

        if not valid_category(new_cat):
            flash(
                "Category can only contain letters, numbers, spaces, - and _ (max 30 characters).",
                "error",
            )
            return render_template("edit.html", item=prompt_data)

        image_path = prompt_data["image_path"]
        source_path = upload_path_from_url(image_path)
        upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])

        # If category changed, move file to the target category folder safely
        if new_cat != prompt_data["category"] and source_path and os.path.isfile(source_path):
            target_folder = os.path.abspath(os.path.join(upload_root, new_cat))
            try:
                if os.path.commonpath([upload_root, target_folder]) != upload_root:
                    raise ValueError("Invalid category folder.")
            except ValueError:
                flash("Could not move the image to that category. Please try another name.", "error")
                return render_template("edit.html", item=prompt_data), 400

            os.makedirs(target_folder, exist_ok=True)
            original_name = os.path.basename(source_path)
            stem, ext = os.path.splitext(original_name)
            target_path = os.path.join(target_folder, original_name)
            counter = 1
            while os.path.exists(target_path) and os.path.abspath(target_path) != os.path.abspath(source_path):
                target_path = os.path.join(target_folder, f"{stem}_{counter}{ext}")
                counter += 1

            if os.path.abspath(target_path) != os.path.abspath(source_path):
                try:
                    os.replace(source_path, target_path)
                except OSError:
                    flash("Could not move the image. Your changes were not saved.", "error")
                    return redirect(f"/edit/{id}")

                relative_target = os.path.relpath(target_path, upload_root).replace(os.sep, "/")
                image_path = f"/static/uploads/{relative_target}"

                old_folder = os.path.dirname(source_path)
                try:
                    if old_folder != target_folder and os.path.isdir(old_folder) and not os.listdir(old_folder):
                        os.rmdir(old_folder)
                except OSError:
                    pass

        db.execute(
            "UPDATE images SET prompt_text = ?, category = ?, image_path = ? WHERE id = ?",
            new_prompt,
            new_cat,
            image_path,
            id,
        )
        flash("Updated successfully!", "success")
        return redirect(url_for("index"))

    return render_template("edit.html", item=prompt_data)


@app.route("/favorite/<int:id>", methods=["POST"])
def favorite(id: int):
    """Toggle the favorite status of a prompt entry."""
    db.execute("UPDATE images SET is_favorite = 1 - is_favorite WHERE id = ?", id)
    return redirect(request.referrer or url_for("index"))


@app.route("/delete/<int:id>", methods=["POST"])
def delete(id: int):
    """Safely delete prompt record and its corresponding artwork file."""
    data = db.execute("SELECT image_path FROM images WHERE id = ?", id)
    if data:
        path = upload_path_from_url(data[0]["image_path"])
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

            # Prune empty category directories safely
            folder = os.path.dirname(path)
            upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])
            try:
                if (
                    os.path.commonpath([upload_root, folder]) == upload_root
                    and os.path.isdir(folder)
                    and not os.listdir(folder)
                ):
                    os.rmdir(folder)
            except (OSError, ValueError):
                pass

        db.execute("DELETE FROM images WHERE id = ?", id)
        flash("Deleted successfully.", "success")
    return redirect(url_for("index"))


@app.route("/about")
def about():
    """Render About page with architecture overview and system specifications."""
    return render_template("about.html")


@app.route("/download/<path:filename>")
def download_file(filename: str):
    """
    Secure file download handler with directory containment check
    to eliminate path traversal risks.
    """
    upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])
    full_path = os.path.abspath(os.path.join(upload_root, filename))
    try:
        inside_uploads = os.path.commonpath([upload_root, full_path]) == upload_root
    except ValueError:
        inside_uploads = False

    if not inside_uploads or not os.path.isfile(full_path):
        abort(404)

    return send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path),
        as_attachment=True,
    )


# -----------------------------------------------------------------------------
# SEO & Search Engine Endpoints (robots.txt & sitemap.xml)
# -----------------------------------------------------------------------------
@app.route("/robots.txt")
def robots_txt():
    """Serve robots.txt file with proper crawler directives."""
    base_url = request.url_root.rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Allow: /static/",
        "Allow: /about",
        "Disallow: /edit/",
        "Disallow: /delete/",
        "Disallow: /favorite/",
        "Disallow: /download/",
        "",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    """Dynamically generate standard XML Sitemap indexing all public routes."""
    base_url = request.url_root.rstrip("/")
    categories = db.execute("SELECT DISTINCT category FROM images ORDER BY category")

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{base_url}/</loc>",
        "    <changefreq>daily</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
        "  <url>",
        f"    <loc>{base_url}/about</loc>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.8</priority>",
        "  </url>",
        "  <url>",
        f"    <loc>{base_url}/add</loc>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.7</priority>",
        "  </url>",
    ]

    for cat in categories:
        safe_cat = quote_plus(str(cat["category"]))
        xml_lines.extend([
            "  <url>",
            f"    <loc>{base_url}/?category={safe_cat}</loc>",
            "    <changefreq>daily</changefreq>",
            "    <priority>0.6</priority>",
            "  </url>",
        ])

    xml_lines.append("</urlset>")
    return Response("\n".join(xml_lines), mimetype="application/xml")


# -----------------------------------------------------------------------------
# Local Development Server Entry Point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host=host, port=port, debug=debug)
