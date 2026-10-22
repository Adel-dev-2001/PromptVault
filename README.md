# PromptVault — AI Prompt Library

CS50x Final Project | by Adel Salah El-Din Ibrahim Ahmed Mohamed

Video Demo: https://youtu.be/-prDHVKBQtc

---

## What is this?

I built PromptVault because I kept losing my best AI prompts. Every time I generated a good image, I'd save the image but forget the exact prompt that made it work. This app solves that: it's a personal library where I can upload an AI-generated image, save the prompt I used, and organize everything by category.

PromptVault does not generate images. It stores images you made elsewhere together with their prompts.

---

## What it does

The app is basically a gallery. You upload an image, paste the prompt you used to create it, and pick a category. From the home page you can:

- browse everything, filter by category, or show only your favorites
- sort by newest or oldest
- mark or unmark an entry as a favorite
- edit an entry's prompt text and category (the image itself stays as uploaded)
- delete an entry, which also deletes its image file
- download an image directly from the gallery

There is also a short About page, and flash messages give feedback after every action.

---

## How to run it

You need Python 3 and `pip`.

1. Open a terminal in the project folder.
2. Create and activate a virtual environment:

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

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the app:
   ```bash
   python app.py
   ```

5. Open http://127.0.0.1:5000 in your browser.

The included `prompts.db` is empty. The `images` table is created automatically the first time the app starts. The page icons (Font Awesome) and fonts (Google Fonts) are loaded from CDNs, so an internet connection is needed to see them.

---

## How I built it

The backend is Python and Flask. I have routes for the main gallery, adding new entries, editing, deleting, favoriting, downloading, and the About page. All data is stored in an SQLite database using the CS50 SQL library. The database has one table called `images` that stores the image path, prompt text, category, whether it's favorited, and a timestamp.

For file uploads I used Werkzeug's `secure_filename` and added validation so only image files (png, jpg, jpeg, gif, webp) are accepted. The check is based on the file extension. Uploaded images are saved in a separate folder for each category (`static/uploads/<Category>/`), which is created when needed. When an entry is deleted, its image is removed, and the category folder is removed too if it is empty.

The frontend is plain HTML, CSS, and a little JavaScript. I used Jinja2 templating with a base layout that all pages extend from. The one JavaScript I wrote is for the image preview on the upload form: it reads the file locally and shows a preview before you submit.

For the design I went with a dark glassmorphism style. I defined everything through CSS variables so colors stay consistent across the whole app. Cards animate in on load with a small stagger delay, and action buttons appear on hover as an overlay so the gallery stays clean.

---

## Files

- `app.py`: all the Flask routes and logic
- `prompts.db`: the SQLite database (empty in the repository)
- `requirements.txt`: Python dependencies
- `.gitignore`: keeps uploaded images and local databases out of Git
- `static/styles.css`: all styling
- `static/favicon.svg`: site icon
- `static/uploads/`: where uploaded images are saved
- `templates/layout.html`: base template
- `templates/index.html`: the main gallery page
- `templates/add.html`: form to add a new prompt
- `templates/edit.html`: form to edit an existing prompt
- `templates/about.html`: about page

---

## Before putting it online

This is a learning project and is meant to run locally. Before exposing it to the internet, replace the hard-coded Flask `secret_key`, turn off `debug=True`, and tighten the handling of the category name and download path, because both are used to build file paths.

---

## Note on AI usage

I used Claude (by Anthropic) as an assistant during development: for debugging, CSS suggestions, and code review. The idea, features, and structure are mine, and I understand how everything works. This is in line with CS50's academic honesty policy.

---

*CS50x Final Project — 2026*
