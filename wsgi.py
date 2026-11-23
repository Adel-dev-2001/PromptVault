"""WSGI entry point for PromptVault."""

import os

os.environ.setdefault("APP_ENV", "production")

from app import app  # noqa: E402

__all__ = ["app"]
