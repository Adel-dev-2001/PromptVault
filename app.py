"""PromptVault: Flask application for storing AI-generated images and their prompts."""

import hmac
import os
import re
import secrets
import sqlite3
from urllib.parse import unquote, urlsplit

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
from PIL import Image, ImageSequence, UnidentifiedImageError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
EXPECTED_IMAGE_FORMATS = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "gif": "GIF",
    "webp": "WEBP",
}
MAX_IMAGE_PIXELS = 20_000_000
MAX_CONTENT_LENGTH = 10 * 1024 * 1024
CATEGORY_PATTERN = re.compile(r"\A[\w \-]{1,30}\Z")
KNOWN_PLACEHOLDER_SECRETS = {
    "change-this-to-a-secure-random-32-byte-hex-string",
    "replace_with_a_secure_production_secret_key_32_bytes",
    "replace-with-a-random-64-char-hex-key",
    "changeme",
    "secret",
}


def resolve_secret_key(logger, is_production: bool) -> str:
    """Return SECRET_KEY from env, or fail in production / warn once in dev."""
    raw = os.environ.get("SECRET_KEY", "").strip()
    invalid = not raw or len(raw) < 32 or raw in KNOWN_PLACEHOLDER_SECRETS
    if not invalid:
        return raw
    if is_production:
        raise RuntimeError(
            "SECRET_KEY must be set to a non-placeholder value of at least 32 chars in production."
        )
    logger.warning(
        "SECRET_KEY is missing, short, or placeholder; generated a temporary development key."
    )
    return secrets.token_hex(32)


app = Flask(__name__)
IS_PRODUCTION = os.environ.get("APP_ENV", "development").strip().lower() == "production"
app.secret_key = resolve_secret_key(app.logger, IS_PRODUCTION)

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION

if os.environ.get("TRUST_PROXY") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


@app.before_request
def require_app_password_for_mutations():
    """Enforce HTTP Basic auth on state-changing requests when APP_PASSWORD is set."""
    expected = app.config.get("APP_PASSWORD")
    if expected is None:
        expected = os.environ.get("APP_PASSWORD", "")
    if not expected or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    auth = request.authorization
    provided = auth.password if auth and auth.type == "basic" else None
    if provided is None or not hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="PromptVault"'},
        )
    return None


# Registered after Basic auth hook so unauthenticated POSTs return 401 before CSRF checks.
csrf = CSRFProtect(app)

default_database_path = os.path.join(app.root_path, "prompts.db")
raw_database_path = os.environ.get("DATABASE_PATH", "").strip()
database_path = os.path.abspath(raw_database_path) if raw_database_path else default_database_path
os.makedirs(os.path.dirname(database_path), exist_ok=True)
sqlite3.connect(database_path).close()
db = SQL(f"sqlite:///{database_path}")

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
db.execute("CREATE INDEX IF NOT EXISTS idx_images_category ON images (category)")
db.execute("CREATE INDEX IF NOT EXISTS idx_images_favorite ON images (is_favorite)")
db.execute("CREATE INDEX IF NOT EXISTS idx_images_timestamp ON images (timestamp)")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    """Return True if filename has an allowed image extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def valid_category(name: str) -> bool:
    """Return True if name is 1-30 Unicode word chars, spaces, hyphens, or underscores."""
    return isinstance(name, str) and bool(name.strip()) and bool(CATEGORY_PATTERN.fullmatch(name))


def upload_path_from_url(image_path: str):
    """Resolve a /static/uploads URL inside UPLOAD_FOLDER, or return None if invalid."""
    prefix = "/static/uploads/"
    if not isinstance(image_path, str) or not image_path.startswith(prefix):
        return None

    relative_path = unquote(image_path[len(prefix) :])
    if "\\" in relative_path or "\x00" in relative_path:
        return None
    upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])
    full_path = os.path.abspath(os.path.join(upload_root, relative_path))
    try:
        if os.path.commonpath([upload_root, full_path]) != upload_root:
            return None
    except ValueError:
        return None
    return full_path


def validate_uploaded_image(file_storage, extension: str) -> None:
    """Verify binary image format and per-frame pixel bounds; resets stream to start."""
    with Image.open(file_storage.stream) as uploaded_image:
        if uploaded_image.format != EXPECTED_IMAGE_FORMATS.get(extension):
            raise ValueError("Image contents do not match the extension.")
        for frame in ImageSequence.Iterator(uploaded_image):
            frame_pixels = frame.width * frame.height
            tile_pixels = 0
            for tile in frame.tile or ():
                if len(tile) >= 2 and isinstance(tile[1], tuple) and len(tile[1]) == 4:
                    x0, y0, x1, y1 = tile[1]
                    tile_pixels = max(tile_pixels, max(0, x1 - x0) * max(0, y1 - y0))
            if max(frame_pixels, tile_pixels) > MAX_IMAGE_PIXELS:
                raise ValueError("Image frame exceeds pixel limit.")
    file_storage.stream.seek(0)
    with Image.open(file_storage.stream) as verified_image:
        verified_image.verify()
    file_storage.stream.seek(0)


def prune_empty_folder(folder: str) -> None:
    """Remove folder if it is empty and inside UPLOAD_FOLDER."""
    upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])
    folder_abs = os.path.abspath(folder)
    try:
        if (
            os.path.commonpath([upload_root, folder_abs]) == upload_root
            and folder_abs != upload_root
            and os.path.isdir(folder_abs)
            and not os.listdir(folder_abs)
        ):
            os.rmdir(folder_abs)
    except (OSError, ValueError):
        pass


def escape_like(value: str) -> str:
    """Escape SQL LIKE wildcard characters so they match literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def safe_same_origin_redirect(referrer: str | None) -> str:
    """Return a relative redirect target when referrer matches request host, else index."""
    if not referrer:
        return url_for("index")
    host_parts = urlsplit(request.host_url)
    ref_parts = urlsplit(referrer)
    same_origin = ref_parts.scheme == host_parts.scheme and ref_parts.netloc == host_parts.netloc
    if same_origin and ref_parts.path.startswith("/") and not ref_parts.path.startswith("//"):
        return f"{ref_parts.path}?{ref_parts.query}" if ref_parts.query else ref_parts.path
    return url_for("index")


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"

    csp_directives = [
        "default-src 'self'",
        "img-src 'self' data: https: blob:",
        # Templates load external stylesheets only and avoid inline style attributes.
        "style-src 'self' https://fonts.googleapis.com https://cdnjs.cloudflare.com",
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com",
        "script-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'self'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


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
    return "Upload too large. The complete request must not exceed 10 MB.", 413


@app.errorhandler(500)
def internal_error(error):
    return render_template("errors/500.html", error=error), 500


@app.route("/")
def index():
    categories = db.execute("SELECT DISTINCT category FROM images ORDER BY category")
    sort = request.args.get("sort", "newest")
    selected_cat = request.args.get("category", "")
    show_fav = request.args.get("favorites", "")
    q = request.args.get("q", "").strip()

    order = "DESC" if sort == "newest" else "ASC"

    clauses = []
    params = []
    if show_fav:
        clauses.append("is_favorite = 1")
    elif selected_cat:
        clauses.append("category = ?")
        params.append(selected_cat)

    if q:
        search_pattern = f"%{escape_like(q)}%"
        # Bind the escape character as a parameter so cs50's sqlparse tokenizer
        # does not mistake literal '\\' for an escaped SQL quote.
        clauses.append("(prompt_text LIKE ? ESCAPE ? OR category LIKE ? ESCAPE ?)")
        params.extend([search_pattern, "\\", search_pattern, "\\"])

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    prompts = db.execute(f"SELECT * FROM images{where_sql} ORDER BY timestamp {order}", *params)

    stats_row = db.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END), 0) AS favorites "
        "FROM images"
    )[0]
    stats = {
        "total": stats_row["total"],
        "favorites": stats_row["favorites"],
        "categories": len(categories),
    }

    prompt_items = [
        {
            "id": p["id"],
            "imagePath": p["image_path"],
            "promptText": p["prompt_text"],
            "category": p["category"],
            "date": str(p["timestamp"])[:10],
            "downloadUrl": url_for(
                "download_file",
                filename=unquote(p["image_path"].removeprefix("/static/uploads/")),
            ),
        }
        for p in prompts
    ]

    return render_template(
        "index.html",
        prompts=prompts,
        prompt_items=prompt_items,
        categories=categories,
        sort=sort,
        selected_cat=selected_cat,
        show_fav=show_fav,
        q=q,
        stats=stats,
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        file = request.files.get("image_file")
        prompt = request.form.get("prompt_text", "").strip()
        cat = request.form.get("category", "").strip(" ").title()

        if not prompt or not cat:
            flash("Please fill in all fields.", "error")
            return render_template("add.html"), 400

        if not valid_category(cat):
            flash(
                "Category can only contain letters, numbers, spaces, - and _ (max 30 characters).",
                "error",
            )
            return render_template("add.html"), 400

        if not file or file.filename == "":
            flash("Please select an image file.", "error")
            return render_template("add.html"), 400

        if not allowed_file(file.filename):
            flash(
                "Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp).",
                "error",
            )
            return render_template("add.html"), 400

        extension = file.filename.rsplit(".", 1)[1].lower()
        try:
            validate_uploaded_image(file, extension)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            flash(
                "Please upload a valid image with matching extension within pixel limits.",
                "error",
            )
            return render_template("add.html"), 400

        stem, ext = file.filename.rsplit(".", 1)
        stem = secure_filename(stem) or "image"
        ext = ext.lower()
        filename = f"{stem}.{ext}"

        cat_folder = os.path.join(app.config["UPLOAD_FOLDER"], cat)
        os.makedirs(cat_folder, exist_ok=True)

        counter = 1
        while os.path.exists(os.path.join(cat_folder, filename)):
            filename = f"{stem}_{counter}.{ext}"
            counter += 1

        file_destination = os.path.join(cat_folder, filename)
        file.save(file_destination)
        image_path = url_for("static", filename=f"uploads/{cat}/{filename}")

        try:
            db.execute(
                "INSERT INTO images (image_path, prompt_text, category) VALUES (?, ?, ?)",
                image_path,
                prompt,
                cat,
            )
        except Exception:
            if os.path.isfile(file_destination):
                os.remove(file_destination)
            prune_empty_folder(cat_folder)
            raise

        flash("Prompt added successfully!", "success")
        return redirect(url_for("index"))

    return render_template("add.html")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id: int):
    rows = db.execute("SELECT * FROM images WHERE id = ?", id)
    if not rows:
        flash("Item not found.", "error")
        return redirect(url_for("index"))

    prompt_data = rows[0]

    if request.method == "POST":
        new_prompt = request.form.get("prompt_text", "").strip()
        new_cat = request.form.get("category", "").strip(" ").title()

        if not new_prompt or not new_cat:
            flash("Please fill in all fields.", "error")
            return render_template("edit.html", item=prompt_data), 400

        if not valid_category(new_cat):
            flash(
                "Category can only contain letters, numbers, spaces, - and _ (max 30 characters).",
                "error",
            )
            return render_template("edit.html", item=prompt_data), 400

        image_path = prompt_data["image_path"]
        source_path = upload_path_from_url(image_path)
        upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])

        if new_cat != prompt_data["category"]:
            if not source_path or not os.path.isfile(source_path):
                flash("Cannot change category because the image file is missing on disk.", "error")
                return render_template("edit.html", item=prompt_data), 400

            target_folder = os.path.abspath(os.path.join(upload_root, new_cat))
            try:
                if os.path.commonpath([upload_root, target_folder]) != upload_root:
                    raise ValueError("Invalid category folder.")
            except ValueError:
                flash("Could not move the image to that category.", "error")
                return render_template("edit.html", item=prompt_data), 400

            os.makedirs(target_folder, exist_ok=True)
            original_name = os.path.basename(source_path)
            stem, ext = os.path.splitext(original_name)
            target_path = os.path.join(target_folder, original_name)
            counter = 1
            while os.path.exists(target_path) and (
                os.path.abspath(target_path) != os.path.abspath(source_path)
            ):
                target_path = os.path.join(target_folder, f"{stem}_{counter}{ext}")
                counter += 1

            if os.path.abspath(target_path) != os.path.abspath(source_path):
                try:
                    os.replace(source_path, target_path)
                except OSError:
                    flash("Could not move the image. Your changes were not saved.", "error")
                    return render_template("edit.html", item=prompt_data), 500

                relative_target = os.path.relpath(target_path, upload_root).replace(os.sep, "/")
                image_path = url_for("static", filename=f"uploads/{relative_target}")
                prune_empty_folder(os.path.dirname(source_path))

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
    rows = db.execute("SELECT id FROM images WHERE id = ?", id)
    if not rows:
        abort(404)
    db.execute("UPDATE images SET is_favorite = 1 - is_favorite WHERE id = ?", id)
    return redirect(safe_same_origin_redirect(request.referrer))


@app.route("/delete/<int:id>", methods=["POST"])
def delete(id: int):
    data = db.execute("SELECT image_path FROM images WHERE id = ?", id)
    if not data:
        abort(404)

    path = upload_path_from_url(data[0]["image_path"])
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
        prune_empty_folder(os.path.dirname(path))

    db.execute("DELETE FROM images WHERE id = ?", id)
    flash("Deleted successfully.", "success")
    return redirect(url_for("index"))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/download/<path:filename>")
def download_file(filename: str):
    decoded = unquote(filename)
    if "\\" in filename or "\\" in decoded or "\x00" in filename or "\x00" in decoded:
        abort(404)
    if any(part == ".." for part in decoded.split("/")):
        abort(404)

    upload_root = os.path.abspath(app.config["UPLOAD_FOLDER"])
    full_path = os.path.abspath(os.path.join(upload_root, decoded))
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


@app.route("/robots.txt")
def robots_txt():
    base_url = request.url_root.rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Allow: /static/",
        "Allow: /about",
        "Disallow: /add",
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
    base_url = request.url_root.rstrip("/")
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
        "</urlset>",
    ]
    return Response("\n".join(xml_lines), mimetype="application/xml")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host=host, port=port, debug=debug)
