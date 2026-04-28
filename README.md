# PromptVault — AI Prompt Library

CS50x Final Project | by [Adel Salah El-Din Ibrahim Ahmed Mohamed]

Video Demo: [https://youtu.be/-prDHVKBQtc]

---

## What is this?

I built PromptVault because I kept losing my best AI prompts. Every time I generated a good image, I'd save the image but forget the exact prompt that made it work. This app solves that — it's a personal library where I can upload an AI-generated image, save the prompt I used, and organize everything by category.

---

## What it does

The app is basically a gallery. You upload an image, paste the prompt you used to create it, and pick a category. From the home page you can browse everything, filter by category, sort by date, and mark your favorites. You can also edit or delete any entry, and download images directly from the gallery.

---

## How I built it

The backend is Python and Flask. I have routes for the main gallery, adding new entries, editing, deleting, favoriting, and downloading. All data is stored in an SQLite database using the CS50 SQL library. The database has one table called `images` that stores the image path, prompt text, category, whether it's favorited, and a timestamp.

For file uploads I used Werkzeug's `secure_filename` and added validation so only image files (png, jpg, jpeg, gif, webp) are accepted. I also added flash messages so the user gets feedback after every action.

The frontend is plain HTML, CSS, and a little JavaScript. I used Jinja2 templating with a base layout that all pages extend from. The one JavaScript I wrote is for the image preview on the upload form — it reads the file locally and shows a preview before you submit.

For the design I went with a dark glassmorphism style. I defined everything through CSS variables so colors stay consistent across the whole app. Cards animate in on load with a small stagger delay, and action buttons appear on hover as an overlay so the gallery stays clean.

---

## Files

- `app.py` — all the Flask routes and logic
- `prompts.db` — the SQLite database
- `static/styles.css` — all styling
- `static/favicon.svg` — site icon
- `static/uploads/` — where uploaded images are saved
- `templates/layout.html` — base template
- `templates/index.html` — the main gallery page
- `templates/add.html` — form to add a new prompt
- `templates/edit.html` — form to edit an existing prompt
- `templates/about.html` — about page

---

## Note on AI usage

I used Claude (by Anthropic) as an assistant during development — for debugging, CSS suggestions, and code review. The idea, features, and structure are mine, and I understand how everything works. This is in line with CS50's academic honesty policy.

---

*CS50x Final Project — 2026*
