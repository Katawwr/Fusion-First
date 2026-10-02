"""`fusion serve`: the web app on this machine, one origin, never drivable by another website.

Three locks: loopback bind; a Host allowlist (defeats DNS rebinding, since a hostile domain still
sends its own name); and a per-launch token injected into the page and required on every
state-changing `/api/` call (other origins cannot read the page or set a custom header cross-site).
"""

from __future__ import annotations

import hmac
import os
import pathlib
import secrets
import socket
import threading
import webbrowser
from collections.abc import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fusion_first.web.factory import create_app
from fusion_first.web.settings import Settings, load_settings

DEFAULT_PORT = 8765
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
TOKEN_HEADER = "X-Fusion-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_BUILD_HINT = "build it with `npm --prefix frontend run build`, or point --dist at a built frontend"


class ServeError(Exception):
    """A launch problem the user can fix (bad host, missing build). The CLI prints it and exits 2."""


def _repo_dist() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _bundled_dist() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1] / "_bundled" / "web"


def find_dist(explicit: str | None = None) -> pathlib.Path:
    """The built frontend: --dist, FUSION_WEB_DIST, the checkout's frontend/dist, then the wheel's copy."""
    chosen = explicit or os.environ.get("FUSION_WEB_DIST")
    candidates = [pathlib.Path(chosen)] if chosen else [_repo_dist(), _bundled_dist()]
    for c in candidates:
        if (c / "index.html").is_file():
            return c
    where = candidates[0] if chosen else " or ".join(str(c) for c in candidates)
    raise ServeError(f"no built frontend (index.html) found at {where}: {_BUILD_HINT}")


def inject_token(index_html: str, token: str) -> str:
    tag = f'<meta name="fusion-token" content="{token}">'
    if "</head>" in index_html:
        return index_html.replace("</head>", tag + "</head>", 1)
    return tag + index_html


class _NoFraming:
    """Deny framing: a framed copy of the token-bearing page would allow clickjacking."""

    _HEADERS = [(b"x-frame-options", b"DENY"), (b"content-security-policy", b"frame-ancestors 'none'")]

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *self._HEADERS]}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _LaunchTokenGate:
    """Refuse any state-changing /api/ request that does not carry this launch's token."""

    def __init__(self, app, token: str):
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["path"].startswith("/api/")
            and scope["method"] not in _SAFE_METHODS
        ):
            supplied = dict(scope["headers"]).get(TOKEN_HEADER.lower().encode(), b"")
            if not hmac.compare_digest(supplied, self._token):
                refusal = JSONResponse(
                    {"detail": "This request did not come from the Fusion page this server opened."},
                    status_code=403,
                )
                await refusal(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_local_app(
    dist: pathlib.Path,
    token: str | None = None,
    settings: Settings | None = None,
    local_backends: bool = True,
    **factory_kwargs,
) -> FastAPI:
    """The API plus the built frontend on one origin, behind the three locks (see module doc)."""
    dist = pathlib.Path(dist).resolve()
    token = token or secrets.token_urlsafe(32)
    settings = (settings or load_settings()).model_copy(
        update={"allow_local_backends": local_backends, "cors_origins": []}
    )
    app = create_app(settings=settings, **factory_kwargs)
    page = inject_token((dist / "index.html").read_text(encoding="utf-8"), token)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "not found")
        target = (dist / path).resolve()
        if path and target.is_file() and target.is_relative_to(dist):
            return FileResponse(target)
        # Client-side routes (/scan, /trust...) and anything unknown get the app page.
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    app.add_middleware(_LaunchTokenGate, token=token)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ALLOWED_HOSTS))
    app.add_middleware(_NoFraming)  # outermost: every response, refusals included
    return app


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def serve(
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    dist: str | None = None,
    open_browser: bool = True,
    local_backends: bool = True,
    run: Callable | None = None,
) -> None:
    """Launch the local app. Blocks until Ctrl+C. Raises ServeError for a fixable launch problem."""
    if host not in ALLOWED_HOSTS:
        raise ServeError(
            f"fusion serve only listens on this machine (127.0.0.1 or localhost), not {host!r}: "
            "it can drive your local models, so it is never exposed to the network"
        )
    app = create_local_app(find_dist(dist), local_backends=local_backends)
    if _port_in_use(port):
        raise ServeError(f"port {port} is in use (is Fusion already running?); try --port {port + 1}")
    url = f"http://127.0.0.1:{port}"
    backends = "on (Ollama, claude CLI)" if local_backends else "off (demo only)"
    print(f"Fusion is running at {url}  (local backends: {backends}). Press Ctrl+C to stop.")
    timer = threading.Timer(1.0, webbrowser.open, args=[url]) if open_browser else None
    if timer:
        timer.start()
    if run is None:
        import uvicorn

        run = uvicorn.run
    try:
        run(app, host="127.0.0.1", port=port, log_level="warning")
    except (OSError, SystemExit) as e:  # uvicorn reports a failed bind as SystemExit(1)
        raise ServeError(f"could not start the server on 127.0.0.1:{port}: {e}") from e
    finally:
        if timer:
            timer.cancel()  # never open a tab onto a server that didn't start
