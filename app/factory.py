"""The FastAPI app factory — pure, importable and testable without `modal` or any provider key.

`create_app()` returns a fully-wired app that runs demo scans with zero keys. Real scans engage
automatically when a provider key is present in settings. The Modal ASGI wrapper (app/modal_app.py)
is the only thing that imports `modal`; it simply calls this factory.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.clients import LiveUnavailable, build_scan_kwargs, resolve_mode
from app.models import GuardrailRequest, HardenRequest, ScanRequest
from app.persistence import InMemoryScanStore
from app.settings import Settings, load_settings
from app.snippet import guardrail_snippet
from app.sse import sse_frame
from fusion.attacks.taxonomy import Crosswalk
from fusion.engine.fixes import apply_fix, guard_block
from fusion.engine.report_html import render_dashboard_html
from fusion.engine.user_scan import run_user_scan
from fusion.judge.rubric import REGISTRY
from fusion.schemas import ScanEvent, ScanEventType, ScanResult, ScanTier
from fusion.security.webhook import verify_signature

_FENCE_TOKENS = ("<untrusted>", "</untrusted>")


def _sanitize_prompt(text: str) -> str:
    """Strip the judge's untrusted-content fence markers from user input so a pasted prompt can't
    forge them into the evaluation transcript."""
    for tok in _FENCE_TOKENS:
        text = text.replace(tok, "")
    return text


def _new_scan_id() -> str:
    return uuid.uuid4().hex[:16]


def create_app(settings: Settings | None = None, store=None, scan_kwargs_builder=None) -> FastAPI:
    settings = settings or load_settings()
    store = store or InMemoryScanStore()
    build_kwargs = scan_kwargs_builder or build_scan_kwargs

    app = FastAPI(title="Fusion First API", version=settings.version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # frontend is a static SPA on another origin; no cookies used
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.store = store

    def _prepare(req) -> tuple[str, list[str], ScanTier, dict]:
        if len(req.system_prompt) > settings.prompt_max_chars:
            raise HTTPException(413, f"system prompt exceeds {settings.prompt_max_chars} characters")
        checks = req.checks or sorted(REGISTRY)
        tier = ScanTier.FULL if req.tier == "full" else ScanTier.QUICK
        try:
            mode = resolve_mode(req.mode, settings)
        except LiveUnavailable as e:
            raise HTTPException(402, str(e)) from e
        kwargs = build_kwargs(mode, settings)
        return _sanitize_prompt(req.system_prompt), checks, tier, kwargs

    def _scan_stream(system_prompt, checks, tier, kwargs, scan_id):
        return run_user_scan(
            system_prompt=system_prompt, checks=checks, tier=tier, target_name="Your prompt", **kwargs
        )

    # ----------------------------------------------------------------- meta

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "mode": "live" if settings.has_live_keys else "demo",
            "version": settings.version,
        }

    @app.get("/api/version")
    def version():
        return {
            "version": settings.version,
            "crosswalk": Crosswalk().code_version(),
            "checks": sorted(REGISTRY),
            "live_available": settings.has_live_keys,
        }

    @app.get("/api/me")
    def me():
        # Auth is wired in M4; anonymous demo scans work today.
        return {"authenticated": False}

    @app.get("/api/credits")
    def credits():
        return {
            "mode": "live" if settings.has_live_keys else "demo",
            "free_scans_per_day": settings.free_scans_per_day,
            "note": "billing not enforced during beta",
        }

    # ----------------------------------------------------------------- scan

    @app.post("/api/scan")
    async def scan(req: ScanRequest):
        system_prompt, checks, tier, kwargs = _prepare(req)
        scan_id = _new_scan_id()
        result: ScanResult | None = None
        async for ev in _scan_stream(system_prompt, checks, tier, kwargs, scan_id):
            if ev.type == ScanEventType.SCAN_COMPLETED and ev.result is not None:
                result = ev.result
        if result is None:
            raise HTTPException(500, "scan produced no result")
        store.put(scan_id, result)
        return {"scan_id": scan_id, "result": result.model_dump(mode="json")}

    @app.post("/api/scan/stream")
    async def scan_stream(req: ScanRequest):
        system_prompt, checks, tier, kwargs = _prepare(req)
        scan_id = _new_scan_id()

        async def gen() -> AsyncIterator[str]:
            # Emit the scan id immediately so the client can fetch/reload even if the stream drops.
            yield sse_frame("scan_id", {"scan_id": scan_id})
            async for ev in _scan_stream(system_prompt, checks, tier, kwargs, scan_id):
                ev: ScanEvent
                if ev.type == ScanEventType.SCAN_COMPLETED and ev.result is not None:
                    store.put(scan_id, ev.result)
                payload = ev.model_dump(mode="json")
                payload["scan_id"] = scan_id
                yield sse_frame(ev.type.value, payload)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/scan/{scan_id}")
    def get_scan(scan_id: str):
        result = store.get(scan_id)
        if result is None:
            raise HTTPException(404, "scan not found")
        return result.model_dump(mode="json")

    @app.get("/api/scan/{scan_id}/report.html", response_class=HTMLResponse)
    def get_report_html(scan_id: str):
        result = store.get(scan_id)
        if result is None:
            raise HTTPException(404, "scan not found")
        title = result.target_name or "Safety Report"
        return HTMLResponse(render_dashboard_html(result.cards, title))

    # ----------------------------------------------------------------- fix

    @app.post("/api/harden")
    def harden(req: HardenRequest):
        checks = req.checks or sorted(REGISTRY)
        hardened = apply_fix(req.system_prompt, checks)
        return {"hardened_prompt": hardened, "guard_block": guard_block(checks), "checks": checks}

    @app.post("/api/guardrail-snippet")
    def guardrail(req: GuardrailRequest):
        checks = req.checks or sorted(REGISTRY)
        return {"language": "python", "snippet": guardrail_snippet(checks), "checks": checks}

    # ----------------------------------------------------------------- webhooks (stubbed effect)

    @app.post("/api/webhooks/billing")
    async def billing_webhook(request: Request):
        body = await request.body()
        signature = request.headers.get("x-signature")
        if not verify_signature(body, signature, settings.webhook_secret):
            raise HTTPException(401, "invalid or missing webhook signature")
        # Signature is real and fail-closed; the billing effect is intentionally a no-op in beta.
        return JSONResponse({"received": True, "applied": False})

    return app
