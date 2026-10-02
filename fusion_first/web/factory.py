"""The FastAPI app factory: runs demo scans with zero keys; app/modal_app.py wraps it for Modal."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from fusion_first.attacks.taxonomy import Crosswalk
from fusion_first.engine.fixes import apply_fix, guard_block
from fusion_first.engine.report_html import render_dashboard_html
from fusion_first.engine.user_scan import run_user_scan
from fusion_first.guardrail.snippet import guardrail_snippet
from fusion_first.judge.rubric import REGISTRY, checks_of_kind
from fusion_first.schemas import ScanEvent, ScanEventType, ScanResult, ScanTier
from fusion_first.web.clients import (
    LiveUnavailable,
    build_scan_kwargs,
    require_backend_allowed,
    resolve_mode,
)
from fusion_first.web.models import GuardrailRequest, HardenRequest, QualityRequest, ScanRequest
from fusion_first.web.persistence import InMemoryScanStore, ScanStore
from fusion_first.web.settings import Settings, load_settings
from fusion_first.web.sse import sse_error, sse_frame, stream_with_heartbeat

_FENCE_TOKENS = ("<untrusted>", "</untrusted>")
CLI_STATUS_TTL_S = 30.0  # how long a `claude auth status` answer is reused by /api/version

log = logging.getLogger(__name__)


def _sanitize_prompt(text: str) -> str:
    """Strip the judge's untrusted-content fence markers so a pasted prompt can't forge them."""
    for tok in _FENCE_TOKENS:
        text = text.replace(tok, "")
    return text


def _new_scan_id() -> str:
    return uuid.uuid4().hex[:16]


def create_app(settings: Settings | None = None, store: ScanStore | None = None, scan_kwargs_builder=None) -> FastAPI:
    settings = settings or load_settings()
    store = store or InMemoryScanStore()
    build_kwargs = scan_kwargs_builder or build_scan_kwargs

    app = FastAPI(title="Fusion First API", version=settings.version)
    app.add_middleware(
        CORSMiddleware,
        # Demo-only servers may answer any origin (no cookies, nothing to spend). A server with local
        # backends enabled spends the host's subscription/CPU, so only its own frontend may call it.
        allow_origins=settings.cors_origins if settings.allow_local_backends else ["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.store = store

    def _prepare(req) -> tuple[str, list[str], ScanTier, dict]:
        if len(req.system_prompt) > settings.prompt_max_chars:
            raise HTTPException(413, f"system prompt exceeds {settings.prompt_max_chars} characters")
        checks = req.checks or checks_of_kind("safety")
        known = set(checks_of_kind("safety")) | set(checks_of_kind("quality"))
        unknown = [c for c in checks if c not in known]
        if unknown:
            raise HTTPException(400, f"unknown checks: {unknown}")
        tier = ScanTier.FULL if req.tier == "full" else ScanTier.QUICK
        quality = [c for c in checks if c in checks_of_kind("quality")]
        if quality and resolve_mode(req.mode, settings) == "demo":
            raise HTTPException(
                400, f"quality checks need a live model (demo responses are canned): {quality}"
            )
        try:
            mode = resolve_mode(req.mode, settings)
            extra = {"target_spec": req.target_spec, "grader_spec": req.grader_spec} if req.backend == "spec" else {}
            kwargs = build_kwargs(mode, settings, req.backend, req.target_model, **extra)
        except LiveUnavailable as e:
            raise HTTPException(402, str(e)) from e
        if req.hardened_prompt is not None:  # measure the prompt the user will actually ship
            if mode == "demo":
                raise HTTPException(400, "an edited prompt needs a live model: demo responses are canned")
            if len(req.hardened_prompt) > settings.prompt_max_chars:
                raise HTTPException(413, f"hardened prompt exceeds {settings.prompt_max_chars} characters")
            kwargs["hardened_prompt"] = _sanitize_prompt(req.hardened_prompt)
        return _sanitize_prompt(req.system_prompt), checks, tier, kwargs

    def _scan_stream(system_prompt, checks, tier, kwargs, scan_id):
        return run_user_scan(
            system_prompt=system_prompt, checks=checks, tier=tier, target_name="Your prompt", **kwargs
        )

    cli_cache: dict = {}  # `claude auth status` spawns a process; the answer is reused briefly

    async def _cli_ready() -> tuple[bool, str]:
        import asyncio
        import time

        from fusion_first.model.providers import claude_cli

        if not settings.allow_local_backends:
            return False, "local backends are off on this server"
        now = time.monotonic()
        if cli_cache and now - cli_cache["at"] < CLI_STATUS_TTL_S:
            return cli_cache["value"]
        value = await asyncio.to_thread(claude_cli.claude_cli_ready)
        cli_cache.update(at=now, value=value)
        return value

    async def _backends() -> dict:
        """Which live backends this server can actually run (not merely whether a key exists)."""
        import asyncio

        from fusion_first.integrations.live import METERED_OPT_IN_ENV, metered_allowed
        from fusion_first.model.providers.ollama import ollama_available, ollama_models
        from fusion_first.web.clients import hosted_keys, web_graders

        local = settings.allow_local_backends
        ollama_ok = local and await asyncio.to_thread(ollama_available)
        cli_ok, cli_reason = await _cli_ready()
        models = [m["name"] for m in await asyncio.to_thread(ollama_models)] if ollama_ok else []
        graders = web_graders(bool(cli_ok), models) if local else []
        keys = hosted_keys() if local else []
        spend = bool(local and metered_allowed("api"))
        hosted = keys if spend else []  # hosted providers usable as a target or a grader
        return {
            "demo": True,
            "cli": bool(cli_ok),
            "cli_reason": cli_reason,
            "ollama": bool(ollama_ok),
            "api": bool(os.environ.get(METERED_OPT_IN_ENV) == "1" and settings.anthropic_api_key),
            "ollama_models": models,
            "local_backends_enabled": bool(local),
            "graders": graders,
            "hosted_providers": hosted,
            "hosted_keys": keys,
            "spend_opt_in": spend,
            "spec": bool(local and (graders or hosted)),
        }

    @app.get("/api/health")
    async def health():
        b = await _backends()
        live = b["cli"] or b["ollama"] or b["api"]
        return {"status": "ok", "mode": "live" if live else "demo", "version": settings.version}

    @app.get("/api/version")
    async def version():
        b = await _backends()
        return {
            "version": settings.version,
            "crosswalk": Crosswalk().code_version(),
            "checks": sorted(REGISTRY),
            "live_available": b["cli"] or b["ollama"] or b["api"],
            "backends": b,
        }

    @app.post("/api/scan")
    async def scan(req: ScanRequest):
        system_prompt, checks, tier, kwargs = _prepare(req)
        scan_id = _new_scan_id()
        result: ScanResult | None = None
        async for ev in _scan_stream(system_prompt, checks, tier, kwargs, scan_id):
            if ev.type == ScanEventType.SCAN_COMPLETED and ev.result is not None:
                result = ev.result
            elif ev.type == ScanEventType.ERROR:
                raise HTTPException(502, {"code": ev.code or "internal", "message": ev.message})
        if result is None:
            raise HTTPException(502, {"code": "internal", "message": "scan produced no result"})
        store.put(scan_id, result)
        return {"scan_id": scan_id, "result": result.model_dump(mode="json")}

    @app.post("/api/scan/stream")
    async def scan_stream(req: ScanRequest):
        system_prompt, checks, tier, kwargs = _prepare(req)
        scan_id = _new_scan_id()

        async def frames() -> AsyncIterator[str]:
            # Emit the scan id immediately so the client can fetch/reload even if the stream drops.
            yield sse_frame("scan_id", {"scan_id": scan_id})
            try:
                async for ev in _scan_stream(system_prompt, checks, tier, kwargs, scan_id):
                    ev: ScanEvent
                    if ev.type == ScanEventType.SCAN_COMPLETED and ev.result is not None:
                        store.put(scan_id, ev.result)
                    payload = ev.model_dump(mode="json")
                    payload["scan_id"] = scan_id
                    yield sse_frame(ev.type.value, payload)
            except Exception:  # noqa: BLE001 (the stream must end with a terminal frame)
                log.exception("scan %s failed", scan_id)
                yield sse_error(
                    "internal", f"The scan failed unexpectedly (ref {scan_id}).", scan_id
                )

        return StreamingResponse(
            stream_with_heartbeat(frames(), settings.sse_heartbeat_s),
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
        return HTMLResponse(render_dashboard_html(result.cards, title, outcomes=result.outcomes))

    @app.post("/api/report.html", response_class=HTMLResponse)
    def post_report_html(result: ScanResult, theme: Literal["dark", "light"] | None = None):
        """Render the result the page already holds (stateless); served as a download, never inline."""
        title = result.target_name or "Safety Report"
        return HTMLResponse(
            render_dashboard_html(result.cards, title, outcomes=result.outcomes, theme=theme),
            headers={"Content-Disposition": 'attachment; filename="fusion-report.html"'},
        )

    @app.post("/api/harden")
    def harden(req: HardenRequest):
        checks = req.checks or checks_of_kind("safety")
        hardened = apply_fix(req.system_prompt, checks)
        return {"hardened_prompt": hardened, "guard_block": guard_block(checks), "checks": checks}

    @app.post("/api/guardrail-snippet")
    def guardrail(req: GuardrailRequest):
        checks = req.checks or checks_of_kind("safety")
        return {"language": "python", "snippet": guardrail_snippet(checks), "checks": checks}

    @app.post("/api/grade-quality")
    async def grade_quality(req: QualityRequest):
        """Quality grading; live-only (402 without a backend)."""
        from fusion_first.integrations import agent_tools
        from fusion_first.integrations.live import LiveUnavailable as FusionLiveUnavailable

        if len(req.system_prompt) > settings.prompt_max_chars:
            raise HTTPException(413, f"system prompt exceeds {settings.prompt_max_chars} characters")
        try:
            require_backend_allowed(req.backend, settings)
            return await agent_tools.grade_quality(
                _sanitize_prompt(req.system_prompt), req.checks, req.target_model, req.backend
            )
        except FusionLiveUnavailable as e:
            raise HTTPException(402, str(e)) from e

    return app
