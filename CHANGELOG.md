# Changelog

All notable changes to PromptVault are documented in this file.

## [1.0.0] - 2026-11-24

Initial public release of PromptVault.

### Added
- Flask and SQLite (`cs50.SQL`) gallery web application for pairing generated images with their prompt text, categories, and favorites (`app.py`, `templates/`, `static/`).
- Separate static GitHub Pages browser demo using browser `localStorage` with HTML attribute escaping and `data:image/` URL validation (`index.html`, `static/js/demo.js`, `404.html`).
- Upload storage outside `static/` under `data/uploads/<Category>/` (configurable via `UPLOAD_FOLDER`) served through explicit `/media/<path:filename>` and `/download/<path:filename>` routes with path containment checks, relative `Category/file.ext` paths in SQLite, startup migration of legacy `/static/uploads/` URL rows and files (without overwriting, pruning empty folders), and `url_for` links compatible with `SCRIPT_NAME` prefixes.
- Upload validation checking extension whitelist, `secure_filename` collision handling, 10 MB request limit, Pillow format verification, per-frame 20 MP ceiling (including animated GIF/WebP frames), and file cleanup on failed database inserts.
- Category editing with on-disk file moves, empty folder pruning, missing-file refusal, and same-origin redirect verification on favorite toggles.
- 24-item gallery pagination (`?page=N`) with `rel="prev"` / `rel="next"` links, page-scoped `#promptDataset` JSON, self-canonical unfiltered pages, 302 redirect on out-of-range page numbers, and SQL `LIKE` wildcard escaping.
- Unicode category normalization (NFC, collapsed inner ASCII spaces) permitting 1-30 chars of `L*`, `M*`, `N*`, space, `-`, `_`, ZWNJ, and ZWJ while rejecting other control/format characters, plus `dir="auto"` BiDi markup and bidi-isolated CSS quotes on prompt cards.
- Optional HTTP Basic authentication via `APP_PASSWORD` (`hmac.compare_digest`, username ignored) using a `PUBLIC_ENDPOINTS` allow-list (`robots_txt` and `static` only) so `/media/`, `/download/`, and all HTML routes require credentials when enabled.
- Production `SECRET_KEY` enforcement (`>= 32` chars, non-placeholder) when `APP_ENV=production` (defaulted in `wsgi.py`, `Procfile`, and `Dockerfile`), plus `CSRFProtect`, CSP (`script-src 'self'`, `img-src 'self' data: blob:`), HSTS over HTTPS (`ProxyFix` via `TRUST_PROXY=1`), versioned `/static/` caching, `/media/` ETag revalidation (`max-age=3600, must-revalidate`), and `Cache-Control: no-store` on form pages.
- Responsive mobile navigation toggle (`aria-expanded`, `aria-controls`), shortened small-screen search placeholder, and a shared focus-trapping modal controller (`PromptVault.createModalController`) with synchronous dialog focus and trigger focus restoration.
- Custom HTML error templates for HTTP 400, 404, 405, 413, and 500, Pillow-generated OG/PWA PNG assets (`scripts/make_social_card.py`), JSON-LD metadata, `/robots.txt`, and `<lastmod>` XML sitemaps.
- Non-root `Dockerfile`, localhost-bound `docker-compose.yml` with a single `/app/data` volume, `.github/dependabot.yml`, `requirements-dev.txt` (`ruff`, `pip-audit`), `SECURITY.md`, GitHub Actions CI (lint, `pip-audit`, unit tests on Python 3.11-3.13 Linux/Windows, Docker build + `curl /`), `unittest` suite (`test_app.py`), and Playwright screenshots (`docs/screenshots/`).
