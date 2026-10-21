"""Geriye uyumlu giriş noktası: ``uvicorn api:app``.

Uygulama ``otogaleri.api`` içindedir.
"""

from otogaleri.api import app

__all__ = ["app"]
