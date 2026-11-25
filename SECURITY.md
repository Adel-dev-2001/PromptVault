# Security Policy

## Supported versions

Fixes are applied to the `main` branch and the current `1.0.x` release.

## Reporting a vulnerability

If you find a security issue in PromptVault, please do not open a public GitHub issue with exploit details. Instead, report it privately through GitHub Security Advisories on the repository (`Security` -> `Advisories` -> `Report a vulnerability`), or contact the maintainer via [GitHub](https://github.com/Adel-dev-2001).

Include the steps to reproduce, the affected route or file, and the Python/Flask environment if relevant.

## Scope and threat model

PromptVault is designed as a single-user local tool. Setting `APP_PASSWORD` adds HTTP Basic authentication (single shared password, username ignored) across all routes including `/media/` and `/download/`, leaving only `/robots.txt` and `/static/` assets public.

The following are out of scope by design:

- Multi-user accounts, session isolation, or per-user permissions.
- Built-in rate limiting or brute-force throttling (handle this at a reverse proxy if exposed outside localhost).
- Malware scanning of uploaded image files beyond Pillow decoding and format/frame validation.

See the Security section in [README.md](README.md) for full details.
