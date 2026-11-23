# Changelog

All notable changes to PromptVault are documented in this file.

## [1.0.0] - 2026-11-23

### Added
- Flask and SQLite (`cs50.SQL`) gallery application for storing image files alongside prompt text, categories, and favorites (`app.py`, `templates/`, `static/`).
- Separate static GitHub Pages browser demo storing entries in `localStorage` (`index.html`, `static/js/demo.js`, `404.html`).
- 24-item gallery pagination (`?page=N`) with `<link rel="prev">` / `<link rel="next">` links, page-scoped `#promptDataset` JSON, self-canonical unfiltered pages, and 302 redirect for out-of-range page numbers.
- Optional single-password HTTP Basic authentication via `APP_PASSWORD` (`hmac.compare_digest`, username ignored) protecting all routes including `/static/uploads/`, leaving `/robots.txt` and public `/static/` assets accessible.
- Responsive mobile navigation menu (`#navToggle` with `aria-expanded` and `aria-controls`) and shortened search placeholder on viewports `<= 768px`.
- Shared accessible modal controller (`PromptVault.createModalController`) with synchronous dialog focus on open, `Tab`/`Shift+Tab` focus trapping, single close path for button/backdrop/`Esc`, and focus restoration to the trigger.
- BiDi support with `dir="auto"` across prompt text, modal text, inputs, and category badges, plus bidi-isolated CSS quotes on gallery cards.
- Custom HTML error templates for HTTP 400, 404, 405, 413, and 500.
- Pillow-generated Open Graph preview card (`static/og-card.png`) and PWA PNG icons (`scripts/make_social_card.py`), plus JSON-LD metadata, `/robots.txt`, and `<lastmod>` XML sitemaps.
- Single-stage non-root `Dockerfile`, localhost-bound `docker-compose.yml`, `Procfile`, `.github/dependabot.yml`, `requirements-dev.txt` (`ruff`, `pip-audit`), and GitHub Actions CI covering lint, dependency audit, unit tests across Python 3.11-3.13 on Linux/Windows, and Docker build + `curl /` smoke check.
- Automated `unittest` suite (`test_app.py`) and Playwright screenshots (`docs/screenshots/`).

### Changed
- Stored relative `Category/file.ext` paths in SQLite with a startup migration from legacy `/static/uploads/...` URLs so `url_for` works under `SCRIPT_NAME` prefixes.
- Resolved upload folder and relative `DATABASE_PATH` values from `app.root_path`, and commented out `DATABASE_PATH` in `.env.example`.
- Normalized category names with Unicode NFC and collapsed inner ASCII spaces, allowing Unicode letters (`L*`), combining marks (`M*`), digits (`N*`), space, `-`, `_`, ZWNJ, and ZWJ (1-30 chars) while rejecting other control/format characters.
- Enforced `SECRET_KEY` (>= 32 chars, non-placeholder) when `APP_ENV=production`, with `wsgi.py`, `Procfile`, and `Dockerfile` defaulting `APP_ENV=production`.
- Added versioned `?v=` static asset URLs (`Cache-Control: public, max-age=31536000, immutable`), upload revalidation (`Cache-Control: public, max-age=3600, must-revalidate` with ETag), and `Cache-Control: no-store` on HTML pages with forms.

### Fixed
- Replaced inline `onclick` prompt interpolation with external deferred scripts and JSON dataset lookups, removing `'unsafe-inline'` from `script-src` and narrowing `img-src` to `'self' data: blob:`.
- Escaped HTML attribute quotes and validated `data:image/` URLs in the static browser demo.
- Escaped SQL `LIKE` wildcards (`%`, `_`, `\`), cleaned up saved files on DB insert failure, refused category changes when the source file is missing on disk, checked animated GIF/WebP per-frame pixel limits, and restricted `/favorite/<id>` redirects to same-origin referrers.
- Fixed modal close-button overlap with category badges, modal `visibility` transition blocking synchronous focus, search icon overlap from CSS specificity, redundant landmark roles, and mismatched `aria-label` attributes.
