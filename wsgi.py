"""
WSGI Production Entry Point for PromptVault
===========================================
Used by production WSGI servers such as Gunicorn or Waitress:
    gunicorn wsgi:app
    waitress-serve --port=5000 wsgi:app
"""

from app import app

if __name__ == "__main__":
    app.run()

