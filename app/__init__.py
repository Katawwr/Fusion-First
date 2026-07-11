"""Fusion First HTTP layer.

Thin FastAPI + Modal wrappers over the pure `fusion/` core. This is the ONLY package where
`modal` may appear — and only in `app/modal_app.py`. Everything else here (the app factory, the
routers, the settings) must import nothing beyond `fusion.*` and the standard web stack, so the
whole API can be built and tested offline with `TestClient(create_app())` and no keys.
"""

from app.factory import create_app

__all__ = ["create_app"]
