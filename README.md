# PromptVault — AI Prompt Library

**CS50x Final Project | by [Adel Mohamed](https://github.com/Adel-dev-2001)**

Video Demo: [https://youtu.be/-prDHVKBQtc](https://youtu.be/-prDHVKBQtc)

---

## Executive Summary & System Overview

In generative artificial intelligence pipelines (e.g., Midjourney, Stable Diffusion, DALL-E, Flux), a persistent industry problem is the **decoupling of generative artwork from its underlying engineering metadata**. Practitioners generate compelling digital imagery, yet frequently lose the complex prompt strings, negative weights, tokens, seed values, and parameter models required to reproduce or refine the work.

**PromptVault** is an enterprise-ready, defensive web application engineered to serve as a high-security digital vault. It provides persistent relational indexing of AI artwork alongside exact prompt engineering parameters, offering category-based taxonomy, live text search, dynamic social graph previews (OpenGraph/Twitter Cards), Schema.org semantic metadata, and strict file validation against polyglot and decompression vulnerabilities.

---

## Academic Statement & Research Pedagogy

### *Official Submission Note for the Russian Government Scholarship Selection Committee*
*(Академическое заявление для комиссии стипендиальной программы Правительства Российской Федерации)*

> ### **Academic Context & Intellectual Inquiry**
> This project was conceptualized, designed, and implemented by Adel Mohamed as a CS50x Final Project capstone within an academic learning trajectory exploring modern computer science, full-stack software architecture, application security, and generative AI tools. The central academic goal was to translate fundamental computing theories—including relational database modeling, defense-in-depth security, and semantic web discovery—into a robust, production-viable software system.
>
> ### **Methodology & Critical Engagement with AI Technologies**
> In alignment with modern academic frameworks that encourage ethical and reflective adoption of cutting-edge computing tools, generative artificial intelligence utilities were employed throughout development as **collaborative pedagogical instruments**. Specifically, large language models were utilized for architectural brainstorming, iterative code review, adversarial security testing, and technical documentation drafting. 
>
> In accordance with academic honesty principles, all architectural patterns, security controls, SQL constraints, and code implementations were critically reviewed, modified, and validated by the author to ensure technical rigor and complete conceptual mastery.
>
> ### **Commitment to Continuous Academic Growth**
> In the spirit of scientific integrity and lifelong scholarly pursuit, the author acknowledges that this codebase represents a significant milestone within an ongoing learning continuum. While enterprise engineering standards—including OWASP Top 10 mitigations, strict CSP headers, parameterized SQL, and a comprehensive 16-point automated test suite—have been rigorously implemented, the author views this work as a living foundation subject to ongoing refinement, peer review, and academic evaluation. Constructive critique and academic inquiry are welcomed as catalysts for continuous mastery.

---

## System Architecture

The application is structured following clean architectural separation of concerns:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Presentation Layer (UI)                         │
│   Jinja2 Templates · Dark Glassmorphism CSS · WCAG Accessible HTML5   │
│   Responsive Layout · Details Modal · Clipboard API · Search Hotkeys   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP Requests / CSRF Tokens
┌───────────────────────────────────▼────────────────────────────────────┐
│                  Application & Middleware Layer (Flask)                │
│   Authentication & CSRF Protection (Flask-WTF)                         │
│   HTTP Security Middleware (CSP, HSTS, X-Frame-Options, Nosniff)       │
│   Dynamic Search & Query Parsing · Error Handlers (400, 403, 404, 500) │
│   SEO Endpoints (/robots.txt & dynamic /sitemap.xml)                   │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
┌───────────────────▼─────────────┐   ┌──────────────▼───────────────────┐
│     Secure File Verification    │   │      Persistence Layer (Data)     │
│   Werkzeug secure_filename      │   │   SQLite Relational Engine        │
│   Pillow Deep Header Inspection │   │   B-Tree Indexes (Category, Fav)  │
│   20 MP Decompression Limit     │   │   Parameterized SQL Statements    │
│   Isolated Directory Sync       │   │   Zero SQL Injection Exposure     │
└─────────────────────────────────┘   └──────────────────────────────────┘
```

---

## Security & Defensive Engineering (OWASP Alignment)

PromptVault is engineered with a **defense-in-depth** security posture:

| Threat Vector | Mitigation Strategy & Implementation | Status |
| :--- | :--- | :---: |
| **Cross-Site Request Forgery (CSRF)** | Synchronizer token pattern enforced via `Flask-WTF` across all state-altering endpoints (`POST /add`, `/edit`, `/delete`, `/favorite`). Unauthenticated or forged submissions trigger HTTP 400. | **Mitigated** |
| **SQL Injection (SQLi)** | 100% of database queries utilize parameterized SQL placeholders (`?`). Dynamic sorting clauses are strictly whitelist-mapped to `("ASC", "DESC")`. | **Mitigated** |
| **Polyglot & Malicious File Uploads** | Multi-phase validation: file extensions are whitelisted (`png`, `jpg`, `jpeg`, `gif`, `webp`), followed by deep raster verification via `PIL.Image.verify()` ensuring byte-header agreement. | **Mitigated** |
| **Decompression Bombs (DoS)** | Total request payload is restricted to 10 MB (`MAX_CONTENT_LENGTH`), and image raster dimensions are strictly capped at 20 million pixels. | **Mitigated** |
| **Path Traversal & LFI** | Canonical filesystem resolution via `os.path.commonpath([upload_root, full_path]) == upload_root`. Traversal sequences (`../`, null bytes) are blocked with HTTP 404. | **Mitigated** |
| **Cross-Site Scripting (XSS)** | Strict `Content-Security-Policy` (CSP) allows only whitelisted style/font CDNs; Jinja2 auto-escapes user inputs; dangerous inline event handlers are removed. | **Mitigated** |
| **Clickjacking & Sniffing** | HTTP headers enforce `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: strict-origin-when-cross-origin`. | **Mitigated** |
| **Hardware Privacy Leakage** | `Permissions-Policy` header explicitly disables `geolocation`, `camera`, `microphone`, and `payment` APIs. | **Mitigated** |

---

## SEO, Semantic Web & Discoverability

PromptVault is fully optimized for search engine crawlers and social media rich snippets:

- **Schema.org Structured Data (JSON-LD):** Implements `WebApplication` on global templates and `ImageGallery` on collection views, enabling rich search engine indexing.
- **OpenGraph & Twitter Cards:** Full metadata coverage (`og:title`, `og:description`, `og:image`, `og:url`, `twitter:card`) ensuring professional preview embeds on Telegram, LinkedIn, X, and WhatsApp.
- **Automated XML Sitemap:** Dynamic `/sitemap.xml` endpoint automatically enumerates all public routes and category filters with update frequencies and priority weightings.
- **Crawler Directives:** Dedicated `/robots.txt` endpoint instructs search engine bots, permitting indexable galleries while safeguarding administrative endpoints.
- **Accessibility & Semantics:** HTML5 landmarks (`<main>`, `<header>`, `<nav>`, `<article>`), dynamic descriptive `alt` tags based on prompt text, keyboard hotkeys (`/` for search, `Esc` for modals), and a screen-reader skip link.

---

## Core Features & Commercial Capabilities

1. **Live Search & Taxonomy Filtering:** Instant search engine querying prompts and categories simultaneously with zero lag.
2. **One-Click Prompt Synchronization:** Integrated clipboard synchronization button copying prompts directly for immediate pasting into Midjourney or Stable Diffusion.
3. **High-Resolution Inspection Modal:** Fullscreen interactive lightbox showcasing high-resolution art previews, complete prompt texts, character counters, and download links.
4. **Dynamic Category Organization:** Images are saved in category-segregated storage on disk (`static/uploads/<Category>/`); updating a category safely reorganizes files on disk without dangling orphaned folders.
5. **Interactive Drag-and-Drop Uploader:** Modern upload zone supporting drag-and-drop, real-time image preview, and one-click suggested category tags.
6. **Dark Glassmorphism Interface:** Responsive, GPU-accelerated aesthetic built with native CSS variables, backdrop blur filters, and micro-animations.

---

## Directory Structure

```
PromptVault-main/
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore rules for virtualenv, DBs, and uploads
├── app.py                    # Core Flask application, routing, and security
├── Procfile                  # Cloud deployment process definition (Render/Heroku)
├── README.md                 # System documentation & academic statement
├── requirements.txt          # Pinned production Python dependencies
├── test_app.py               # Comprehensive 16-point automated test suite
├── wsgi.py                   # Production WSGI server entry point
├── static/
│   ├── favicon.svg           # High-resolution vector lock icon
│   ├── styles.css            # Dark glassmorphism styles & responsive layout
│   └── uploads/
│       └── .gitkeep          # Upload directory anchor
└── templates/
    ├── layout.html           # Base layout (SEO, OpenGraph, JSON-LD, Navigation)
    ├── index.html            # Main gallery, search, stats banner & lightbox modal
    ├── add.html              # Drag-and-drop upload form with category suggestions
    ├── edit.html             # Edit prompt form with live preview
    ├── about.html            # System architecture, specs & academic statement
    └── errors/
        ├── 400.html          # Custom Bad Request & CSRF error page
        ├── 403.html          # Custom Forbidden error page
        ├── 404.html          # Custom Page Not Found page
        ├── 413.html          # Custom Payload Too Large page
        └── 500.html          # Custom Server Error page
```

---

## Local Setup & Installation

### Prerequisites
- Python 3.10+ (Tested through Python 3.15)
- Git & pip

### 1. Clone the Repository
```bash
git clone https://github.com/Adel-dev-2001/PromptVault.git
cd PromptVault
```

### 2. Configure Virtual Environment

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
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Configure your custom `SECRET_KEY` or allow PromptVault to generate an ephemeral cryptographically secure key at runtime.

### 5. Run Automated Tests
```bash
python -m unittest -v test_app.py
```

### 6. Launch the Application
```bash
python app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## Production Deployment Guide

PromptVault includes a standard WSGI entry point (`wsgi.py`) for enterprise deployment:

### Deployment with Gunicorn (Linux / Container)
```bash
pip install gunicorn
gunicorn --workers 4 --bind 0.0.0.0:5000 wsgi:app
```

### Deployment with Waitress (Windows Production Server)
```bash
pip install waitress
waitress-serve --port=5000 wsgi:app
```

### Docker Deployment
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:5000", "wsgi:app"]
```

---

## Automated Testing & Verification

The application is accompanied by a comprehensive test suite in `test_app.py`, achieving 100% pass rates across 16 critical test cases:

1. `test_gallery_and_headers`: Validates HTTP 200 response and `X-Content-Type-Options: nosniff`.
2. `test_security_headers_and_csp`: Verifies Content-Security-Policy, X-Frame-Options, and Permissions-Policy.
3. `test_missing_csrf_is_rejected`: Confirms all mutating endpoints reject requests lacking valid CSRF tokens.
4. `test_valid_image_upload_and_download`: Tests end-to-end binary upload, database registration, and safe retrieval.
5. `test_fake_image_rejected`: Asserts non-image byte streams masquerading with image extensions are rejected.
6. `test_mismatched_extension_rejected`: Verifies header/extension discrepancy detection.
7. `test_invalid_category_rejected`: Tests regex rejection of path traversal characters in category names.
8. `test_search_filtering`: Validates safe parameterized search across prompt text and categories.
9. `test_favorite_filter_survives_sort`: Confirms persistence of query state across combined filters and sorts.
10. `test_edit_and_delete`: Tests full lifecycle mutation and safe disk cleanup.
11. `test_edit_category_moves_image_file`: Confirms dynamic filesystem directory relocation upon category modification.
12. `test_request_size_limit`: Confirms HTTP 413 response upon payload limit breach.
13. `test_download_traversal_rejected`: Validates path traversal attempts (`../`) are safely halted with HTTP 404.
14. `test_robots_and_sitemap`: Confirms `/robots.txt` and `/sitemap.xml` conform to search engine specifications.
15. `test_schema_json_ld_present`: Verifies presence of valid Schema.org semantic metadata.
16. `test_custom_404_template`: Verifies themed custom error handling.

---

## Technology Stack

- **Backend Runtime:** Python 3.13+
- **Web Framework:** Flask 3.1.3
- **Security & Forms:** Flask-WTF 1.3.0 / Werkzeug 3.1.9
- **Image Processing & Verification:** Pillow (PIL) 13.0.0
- **Database:** SQLite 3 with parameterized queries & B-tree indexes
- **Frontend Engine:** Jinja2 templating, Semantic HTML5, CSS3 Glassmorphism
- **Iconography & Fonts:** FontAwesome 6.4.0 & Google Fonts (Space Mono / DM Sans)
- **Metadata Standards:** Schema.org (JSON-LD), OpenGraph Protocol, Twitter Cards

---

## License & Attribution

Developed by **[Adel Mohamed](https://github.com/Adel-dev-2001)** — GitHub: [@Adel-dev-2001](https://github.com/Adel-dev-2001)  
*Presented as a CS50x Final Project and Academic Portfolio Capstone.*  
*Licensed under the [MIT License](LICENSE).*
