"""Fusion First HTTP layer: the Modal wrapper (`modal_app.py`, the only place `modal` is imported)."""

from app.factory import create_app

__all__ = ["create_app"]
