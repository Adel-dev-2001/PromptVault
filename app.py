import os
import re
import sqlite3
from cs50 import SQL
from flask import Flask, render_template, request, redirect, send_from_directory, flash, abort
from werkzeug.utils import secure_filename
# AI-assisted portfolio hardening with v0 (2026-10-26): CSRF, image verification,
# upload limits, category full-match validation, and response headers.
# These changes are separate from the original CS50x submission.
from flask_wtf.csrf import CSRFProtect
from PIL import Image, UnidentifiedImageError

app = Flask(__name__)
# Secret key for flash messages: set the SECRET_KEY environment variable, otherwise a random key is used
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# Upload settings
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
CSRFProtect(app)

# Category names are used as folder names, so only letters, numbers, spaces, - and _ are allowed
CATEGORY_PATTERN = re.compile(r"^[\w \-]{1,30}$")

# CS50 SQL requires the SQLite file to exist before opening it.
database_path = os.path.abspath('prompts.db')
sqlite3.connect(database_path).close()
db = SQL(f'sqlite:///{database_path}')

# Create table if it doesn't exist
db.execute("""
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_path TEXT,
        prompt_text TEXT,
        category TEXT,
        is_favorite INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def valid_category(name):
    return bool(CATEGORY_PATTERN.fullmatch(name))


@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=63072000'
    return response


@app.errorhandler(413)
def upload_too_large(error):
    return 'Upload too large. The complete request must not exceed 10 MB.', 413


@app.route("/")
def index():
    categories = db.execute("SELECT DISTINCT category FROM images ORDER BY category")
    sort = request.args.get("sort", "newest")
    selected_cat = request.args.get("category", "")
    show_fav = request.args.get("favorites", "")
    order = "DESC" if sort == "newest" else "ASC"

    if show_fav:
        prompts = db.execute("SELECT * FROM images WHERE is_favorite = 1 ORDER BY timestamp " + order)
    elif selected_cat:
        prompts = db.execute("SELECT * FROM images WHERE category = ? ORDER BY timestamp " + order, selected_cat)
    else:
        prompts = db.execute("SELECT * FROM images ORDER BY timestamp " + order)

    return render_template("index.html", prompts=prompts, categories=categories,
                           sort=sort, selected_cat=selected_cat, show_fav=show_fav)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        file = request.files.get('image_file')
        prompt = request.form.get("prompt_text", "").strip()
        cat = request.form.get("category", "").strip().title()

        if not prompt or not cat:
            flash("Please fill in all fields.", "error")
            return render_template("add.html")

        if not valid_category(cat):
            flash("Category can only contain letters, numbers, spaces, - and _ (max 30 characters).", "error")
            return render_template("add.html")

        if file and file.filename != '':
            if not allowed_file(file.filename):
                flash("Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp).", "error")
                return render_template("add.html")

            expected_formats = {
                'png': 'PNG', 'jpg': 'JPEG', 'jpeg': 'JPEG',
                'gif': 'GIF', 'webp': 'WEBP',
            }
            extension = file.filename.rsplit('.', 1)[1].lower()
            try:
                with Image.open(file.stream) as uploaded_image:
                    if uploaded_image.format != expected_formats[extension]:
                        raise ValueError('Image contents do not match the extension.')
                    if uploaded_image.width * uploaded_image.height > 20_000_000:
                        raise ValueError('Image dimensions are too large.')
                    uploaded_image.verify()
                file.stream.seek(0)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                flash('Please upload a valid image, with matching extension and at most 20 million pixels.', 'error')
                return render_template('add.html'), 400

            # Clean the file name, and never overwrite an existing image with the same name
            stem, ext = file.filename.rsplit('.', 1)
            stem = secure_filename(stem) or "image"
            ext = ext.lower()
            filename = stem + "." + ext

            # Create a separate folder for each category
            cat_folder = os.path.join(app.config['UPLOAD_FOLDER'], cat)
            if not os.path.exists(cat_folder):
                os.makedirs(cat_folder)

            counter = 1
            while os.path.exists(os.path.join(cat_folder, filename)):
                filename = stem + "_" + str(counter) + "." + ext
                counter += 1

            file.save(os.path.join(cat_folder, filename))
            image_path = "/static/uploads/" + cat + "/" + filename

            db.execute("INSERT INTO images (image_path, prompt_text, category) VALUES (?, ?, ?)",
                       image_path, prompt, cat)
            flash("Prompt added successfully!", "success")
            return redirect("/")
        else:
            flash("Please select an image file.", "error")

    return render_template("add.html")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    rows = db.execute("SELECT * FROM images WHERE id = ?", id)
    if not rows:
        flash("Item not found.", "error")
        return redirect("/")

    prompt_data = rows[0]

    if request.method == "POST":
        new_prompt = request.form.get("prompt_text", "").strip()
        new_cat = request.form.get("category", "").strip().title()

        if not new_prompt or not new_cat:
            flash("Please fill in all fields.", "error")
            return render_template("edit.html", item=prompt_data)

        if not valid_category(new_cat):
            flash("Category can only contain letters, numbers, spaces, - and _ (max 30 characters).", "error")
            return render_template("edit.html", item=prompt_data)

        db.execute("UPDATE images SET prompt_text = ?, category = ? WHERE id = ?",
                   new_prompt, new_cat, id)
        flash("Updated successfully!", "success")
        return redirect("/")

    return render_template("edit.html", item=prompt_data)


@app.route("/favorite/<int:id>", methods=["POST"])
def favorite(id):
    db.execute("UPDATE images SET is_favorite = 1 - is_favorite WHERE id = ?", id)
    return redirect(request.referrer or "/")


@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    data = db.execute("SELECT image_path FROM images WHERE id = ?", id)
    if data:
        # Delete the image file from disk
        path = data[0]["image_path"].lstrip('/')
        if os.path.exists(path):
            os.remove(path)

        # If the category folder is now empty, remove it too
        folder = os.path.dirname(path)
        if os.path.exists(folder) and not os.listdir(folder):
            os.rmdir(folder)

        db.execute("DELETE FROM images WHERE id = ?", id)
        flash("Deleted successfully.", "success")
    return redirect("/")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route('/download/<path:filename>')
def download_file(filename):
    # filename may include a subfolder e.g. "Cyberpunk/image.png"
    # Only files that really are inside the uploads folder can be downloaded
    upload_root = os.path.abspath(app.config['UPLOAD_FOLDER'])
    full_path = os.path.abspath(os.path.join(upload_root, filename))
    if not full_path.startswith(upload_root + os.sep) or not os.path.isfile(full_path):
        abort(404)
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path), as_attachment=True)


if __name__ == "__main__":
    # Debug mode is off unless you set FLASK_DEBUG=1
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
