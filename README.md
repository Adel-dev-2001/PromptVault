<div align="center">
  <img src="static/favicon.svg" alt="PromptVault Logo" width="88" />
  <h1>PromptVault</h1>
  <h3>AI Prompt Library &amp; Image Asset Manager</h3>
  <p>CS50x Final Project | Built and maintained by <a href="https://github.com/Adel-dev-2001"><strong>Adel Mohamed</strong></a></p>
  <p>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.13%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python" /></a>
    <a href="https://flask.palletsprojects.com/"><img src="https://img.shields.io/badge/Flask-3.1.3-000000?style=flat-square&amp;logo=flask&amp;logoColor=white" alt="Flask" /></a>
    <a href="https://www.sqlite.org/"><img src="https://img.shields.io/badge/Database-SQLite_3-003B57?style=flat-square&amp;logo=sqlite&amp;logoColor=white" alt="SQLite" /></a>
    <a href="https://python-pillow.org/"><img src="https://img.shields.io/badge/Imaging-Pillow_13.0-3b82f6?style=flat-square" alt="Pillow" /></a>
    <a href="#automated-test-suite"><img src="https://img.shields.io/badge/Tests-16_Passing-2ea44f?style=flat-square" alt="Tests" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2ea44f?style=flat-square" alt="License: MIT" /></a>
  </p>
  <p>
    <a href="https://adel-dev-2001.github.io/PromptVault/"><strong>Live Web App</strong></a> |
    <a href="https://youtu.be/-prDHVKBQtc"><strong>Video Demonstration</strong></a> |
    <a href="https://github.com/Adel-dev-2001/PromptVault"><strong>Source Repository</strong></a>
  </p>
</div>

---

## Overview

**PromptVault** is a full-stack web application built with Python, Flask, and SQLite for storing, categorizing, and retrieving AI-generated images alongside the exact prompts used to create them. When working with image generation models (such as Midjourney, Stable Diffusion, DALL-E, or Flux), users frequently save the output image but lose the prompt text, negative prompts, and parameter settings that produced it. PromptVault keeps the artwork and its prompt together in a searchable local library.

Note that PromptVault does not generate images itself. Instead, it acts as a dedicated library and asset manager for organizing images generated elsewhere together with their prompt metadata.

---

## Academic & Learning Context Note

> **Note for Academic Reviewers and Evaluation Committees:**
>
> This project was developed by **Adel Mohamed** (originally created as a CS50x Final Project and further refined as part of a self-directed learning journey in software engineering, backend web development, application security, and AI workflow tooling). The primary educational goals of building PromptVault were to gain hands-on experience in:
> - Designing server-rendered web applications using Python, Flask, and Jinja2 templates.
> - Managing relational data in SQLite with parameterized queries and B-tree indexes.
> - Implementing defensive file upload validation (verifying binary image headers with Pillow, enforcing payload and pixel limits, and preventing path traversal vulnerabilities).
> - Applying web security best practices, including CSRF protection, strict HTTP security headers (CSP, Nosniff, X-Frame-Options), and automated unit testing with Python's `unittest` framework.
>
> Because this application was built as an educational project while actively learning and experimenting with these technologies, certain architectural patterns or edge cases may still have room for further refinement and optimization. Constructive feedback and academic review are always welcome as part of this ongoing learning process.

---

## Key Features

### 1. Gallery, Live Search & Filtering
- **Real-Time Search (`/q`):** Search across saved prompt text and category names directly from the main gallery toolbar, with a global `/` keyboard shortcut to focus the search input.
- **Category & Favorites Filtering:** Filter the library by dynamically generated category chips or view only favorited prompts.
- **Chronological Sorting:** Sort entries by newest or oldest while preserving active search queries, category filters, and favorite views.
- **Vault Metrics Banner:** Displays live counters for total prompts stored, active categories, and favorited entries.

### 2. Prompt Inspection & Clipboard Workflow
- **One-Click Prompt Copy:** Copy any prompt directly to the system clipboard from the gallery card or detail modal, accompanied by a non-intrusive toast notification.
- **High-Resolution Detail Modal:** Open a fullscreen lightbox view for any entry to inspect the full-resolution image, complete prompt text, character count, creation date, and direct download link (`Esc` key supported).

### 3. Upload Pipeline & File Organization
- **Interactive Drag-and-Drop Upload (`/add`):** Supports both file browsing and drag-and-drop image selection with instant client-side image preview, live character counting, and quick-fill category suggestion tags.
- **Category-Based Directory Sync:** Uploaded images are stored under `static/uploads/<Category>/`. If a duplicate filename exists in the same category, an incremental suffix (for example, `artwork_1.png`) is appended automatically so existing files are never overwritten.
- **Automatic File Relocation on Edit (`/edit/<id>`):** Updating an entry's category automatically moves the image file on disk to the new category directory, updates the database path, and removes the old directory if it becomes empty.
- **Clean Deletion (`/delete/<id>`):** Deleting an entry removes both the database record and the underlying image file from disk, pruning the category folder if no other files remain.

---

## Security & SEO Implementation

### Security Measures
- **CSRF Protection:** All state-changing `POST` routes (`/add`, `/edit/<id>`, `/delete/<id>`, `/favorite/<id>`) require valid CSRF tokens managed by `Flask-WTF`. Missing or invalid tokens return `HTTP 400`.
- **Deep Image Verification:** Uploaded files are checked against an explicit extension whitelist (`png`, `jpg`, `jpeg`, `gif`, `webp`), sanitized via Werkzeug's `secure_filename`, and opened with `PIL.Image` to verify that the actual binary image format matches the file extension.
- **Decompression Bomb & Payload Limits:** Complete HTTP requests are capped at `10 MB` (`MAX_CONTENT_LENGTH`), and image dimensions are restricted to a maximum of `20,000,000` pixels (`MAX_IMAGE_PIXELS`).
- **Path Traversal Prevention:** Category names are validated with a strict regular expression (`^[\w \-]{1,30}$`). File resolution in `upload_path_from_url()` and `/download/<path:filename>` verifies canonical containment via `os.path.commonpath` so files outside `static/uploads/` can never be read, moved, or deleted.
- **Parameterized SQL Queries:** All user-supplied values are bound via parameterized SQL placeholders (`?`), preventing SQL injection across search, filter, insert, and update operations.
- **HTTP Security Headers:** Every response includes `Content-Security-Policy` (CSP), `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy` (disabling camera, microphone, geolocation, and payment APIs).

### SEO & Structured Data
- **Metadata & Social Cards:** Configured in `templates/layout.html` with canonical URLs, meta descriptions, keywords, Open Graph (`og:*`) tags, and Twitter Card metadata.
- **Schema.org JSON-LD:** Embeds structured data graphs for `WebApplication` (site-wide) and `ImageGallery` (on the main gallery view).
- **Search Engine Endpoints:** Provides dynamic `/robots.txt` and `/sitemap.xml` routes, plus a Web App Manifest (`static/manifest.json`) and custom vector icon (`static/favicon.svg`).
- **Semantic HTML & Accessibility:** Uses semantic HTML5 landmarks (`<header>`, `<nav>`, `<main>`, `<article>`, `<footer>`), dynamic `alt` attributes derived from prompt text, ARIA labels on icon buttons, and a keyboard skip-to-content link.

---

## Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Backend Framework** | Python 3.13+ & Flask 3.1.3 |
| **Database** | SQLite 3 (via CS50 SQL & `sqlite3` with B-tree indexes) |
| **Security & Forms** | Flask-WTF 1.3.0 (CSRF Protection) & Werkzeug 3.1.9 |
| **Image Verification** | Pillow (PIL) 13.0.0 |
| **Frontend Templates** | Jinja2, Semantic HTML5, Vanilla JavaScript |
| **Styling** | Custom CSS3 (Dark Glassmorphism, CSS Variables, Responsive Grid) |
| **Production WSGI** | Gunicorn (Linux/Docker) / Waitress (Windows) |

---

## Project Structure

```text
PromptVault/
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI pipeline running the 16 unit tests
├── static/
│   ├── favicon.svg                 # Custom SVG vault icon matching the header logo
│   ├── manifest.json               # Web App Manifest for PWA & mobile metadata
│   ├── styles.css                  # Main stylesheet (dark glassmorphism & responsive layout)
│   └── uploads/
│       └── .gitkeep                # Preserves the uploads directory in Git
├── templates/
│   ├── errors/                     # Custom HTTP error pages (400, 403, 404, 413, 500)
│   ├── about.html                  # Project overview, security specs, and academic note
│   ├── add.html                    # Upload form with drag-and-drop preview & tag pills
│   ├── edit.html                   # Edit prompt text and category form
│   ├── index.html                  # Main gallery, search bar, filters, and detail modal
│   └── layout.html                 # Base template (SEO meta tags, JSON-LD, nav, footer)
├── .env.example                    # Example environment variable configuration
├── .gitignore                      # Excludes .venv, __pycache__, *.db, and uploaded images
├── .nojekyll                       # Disables Jekyll processing for GitHub Pages deployment
├── 404.html                        # Static 404 fallback page for GitHub Pages
├── app.py                          # Main Flask application, routes, validation, and headers
├── Dockerfile                      # Production container definition
├── docker-compose.yml              # Docker Compose service and persistent volume config
├── index.html                      # Interactive client-side web app for GitHub Pages live demo
├── LICENSE                         # MIT License
├── Procfile                        # Process definition for cloud platforms (Render/Heroku)
├── README.md                       # Project documentation
├── requirements.txt                # Pinned Python dependencies
├── robots.txt                      # Static crawler directives for GitHub Pages
├── sitemap.xml                     # Static XML sitemap for GitHub Pages
├── test_app.py                     # Automated unit test suite (16 test cases)
└── wsgi.py                         # WSGI entry point for production servers
```

---

## Getting Started Locally

### Prerequisites
- **Python** (3.10 or newer; tested through Python 3.15)
- **pip** (Python package installer)

### 1. Clone the Repository
```bash
git clone https://github.com/Adel-dev-2001/PromptVault.git
cd PromptVault
```

### 2. Create and Activate a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (Optional)
Copy `.env.example` to `.env` if you want to set a persistent `SECRET_KEY` or custom port:
```bash
cp .env.example .env
```
If `SECRET_KEY` is not set, the app generates a random 32-byte key on startup.

### 5. Run the Automated Test Suite
```bash
python -m unittest -v test_app.py
```

### 6. Start the Application
```bash
python app.py
```
Open `http://127.0.0.1:5000` in your browser. The SQLite database (`prompts.db`) and `images` table are created automatically on first run.

---

## Production Deployment

PromptVault includes `wsgi.py`, `Procfile`, `Dockerfile`, and `docker-compose.yml` for running in production environments:

### Option 1: Gunicorn (Linux / macOS)
```bash
pip install gunicorn
gunicorn --workers 4 --bind 0.0.0.0:5000 wsgi:app
```

### Option 2: Waitress (Windows)
```powershell
pip install waitress
waitress-serve --port=5000 wsgi:app
```

### Option 3: Docker Compose
```bash
docker compose up -d --build
```

---

## Automated Test Suite

The `test_app.py` suite runs 16 isolated unit tests in a temporary workspace to verify all routes and security boundaries:

1. `test_gallery_and_headers`: Checks `GET /` status (`200 OK`) and `X-Content-Type-Options: nosniff`.
2. `test_security_headers_and_csp`: Verifies `Content-Security-Policy`, `X-Frame-Options`, and `Permissions-Policy` headers.
3. `test_missing_csrf_is_rejected`: Ensures `POST` requests to `/add`, `/edit/1`, `/delete/1`, and `/favorite/1` without a CSRF token return `HTTP 400`.
4. `test_valid_image_upload_and_download`: Verifies uploading a valid PNG image, storing its database record, and downloading the file from `/download/<path>`.
5. `test_fake_image_rejected`: Confirms non-image binary data with a `.png` extension is rejected with `HTTP 400`.
6. `test_mismatched_extension_rejected`: Confirms a PNG file renamed to `.jpg` is rejected when Pillow inspects the header.
7. `test_invalid_category_rejected`: Verifies path traversal strings (`../outside`) and control characters in category names are rejected.
8. `test_search_filtering`: Tests live search queries (`/?q=...`) for both matching and non-matching terms.
9. `test_favorite_filter_survives_sort`: Ensures favorite filtering (`favorites=1`) persists across sort order toggles (`sort=oldest`).
10. `test_edit_and_delete`: Tests updating prompt text and category, followed by deleting the entry and verifying file removal on disk.
11. `test_edit_category_moves_image_file`: Confirms changing an entry's category moves the image file to the new category folder and cleans up the old folder.
12. `test_request_size_limit`: Verifies requests exceeding `MAX_CONTENT_LENGTH` return `HTTP 413`.
13. `test_download_traversal_rejected`: Confirms `/download/../prompts.db` is blocked with `HTTP 404`.
14. `test_robots_and_sitemap`: Validates `/robots.txt` (`text/plain`) and `/sitemap.xml` (`application/xml`).
15. `test_schema_json_ld_present`: Checks that `WebApplication` and `ImageGallery` JSON-LD schemas render in the HTML output.
16. `test_custom_404_template`: Verifies unknown routes return `HTTP 404` using the custom error template.

---

## Author

- **Adel Mohamed**
- **GitHub:** [@Adel-dev-2001](https://github.com/Adel-dev-2001)
- **Repository:** [github.com/Adel-dev-2001/PromptVault](https://github.com/Adel-dev-2001/PromptVault)

---

## License

This project is licensed under the [MIT License](LICENSE).
