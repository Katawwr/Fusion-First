"""Scan mode resolution and live-client assembly — the one place the web app decides demo vs real.

A `live` request without an available backend fails closed (LiveUnavailable → 402); we NEVER
silently serve a demo card when a real one was asked for. Backend selection is DELEGATED to
`fusion.integrations.live.build_live_clients`, so the web app, CLI and MCP share one zero-spend
policy:

  * "cli" / "auto" (default) — the server's `claude` CLI on subscription auth (no key).
  * "ollama" — a local OPEN-WEIGHT target (Llama/Qwen/Gemma…), judged by Claude over the CLI.
  * "api"    — METERED provider keys. Only with the operator's explicit FUSION_ALLOW_API_SPEND=1;
               an API key merely present in the environment is never used.
  * "spec"   — any model by spec (openai:, hf:, anthropic:, openai-compat: ...) graded by any chat
               grader, on a local server only. cmd:/python: and the host grader stay CLI/MCP-only.
"""

from __future__ import annotations

import os

from fusion.integrations.live import LiveUnavailable, build_live_clients, judge_trust_kwargs
from fusion.web.settings import Settings

__all__ = ["LiveUnavailable", "build_scan_kwargs", "require_backend_allowed", "resolve_mode"]

DEFAULT_OLLAMA_MODEL = "llama3.2:1b"


def resolve_mode(requested: str | None, settings: Settings) -> str:
    # Availability is decided in build_scan_kwargs (which fails closed per backend).
    # "None"/"demo" stays the safe, keyless default.
    return "live" if requested == "live" else "demo"


def _target_model(backend: str | None, target_model: str | None, settings: Settings) -> str:
    if target_model:
        return target_model
    if backend == "ollama":
        # A Claude model id means nothing to Ollama; use a local open-weight default instead.
        return os.environ.get("FUSION_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return settings.target_model


SPEC_BACKEND = "spec"
LOCAL_BACKENDS = ("auto", "cli", "ollama", SPEC_BACKEND)


def require_backend_allowed(backend: str | None, settings: Settings) -> str:
    """Resolve the backend and refuse local backends unless this server enabled them."""
    prefer = backend or "auto"
    if prefer in LOCAL_BACKENDS and not settings.allow_local_backends:
        raise LiveUnavailable(
            "live scans on this server are disabled: local backends (the claude CLI subscription, "
            "Ollama) are off unless the server runs with FUSION_ALLOW_LOCAL_BACKENDS=1 (local use only)"
        )
    return prefer


def _spec_scan_kwargs(settings: Settings, target_spec: str | None, grader_spec: str | None) -> dict:
    """Any model by spec, graded by any chat grader — only what a local page may start: no program
    (cmd:), no in-process function (python:), no host grader (a web scan has no calling agent)."""
    from fusion.backends.resolve import (
        OPAQUE_BACKENDS,
        BackendUnavailable,
        SpecError,
        build_grader_client,
        build_target_client,
        parse_grader,
        parse_target,
    )
    from fusion.model.registry import JudgeChoice
    from fusion.runs.engine import independence_of

    if not (target_spec or "").strip():
        raise LiveUnavailable("an Any-model scan needs a target spec, e.g. openai:gpt-4o-mini")
    try:
        t = parse_target(target_spec)
        g = parse_grader(grader_spec or "claude-cli")
    except SpecError as e:
        raise LiveUnavailable(f"invalid target or grader spec: {e}") from e
    grader_target = parse_target(g.model or "") if g.kind == "target" else None
    if t.backend in OPAQUE_BACKENDS or (grader_target and grader_target.backend in OPAQUE_BACKENDS):
        raise LiveUnavailable("cmd: and python: run code on this machine, so a web page can't start them: "
                              "use the command line (fusion run start)")
    if g.external:
        raise LiveUnavailable("the host grader is the calling agent and a web scan has none: choose claude-cli "
                              "or a chat grader, or grade over MCP")
    try:
        target = build_target_client(t, max_calls=settings.scan_max_calls, allow_command=False)
        judge = build_grader_client(g, max_calls=max(1000, 8 * settings.scan_max_calls), allow_command=False)
    except (BackendUnavailable, SpecError) as e:
        raise LiveUnavailable(str(e)) from e
    independence, disclosure = independence_of(t.label, g.label)
    choice = JudgeChoice(judge_id=g.label, independence=independence, disclosure=disclosure)
    return {"demonstration": False, "judge_client": judge, "target_client": target, "target_model_id": t.model,
            "judge_model": g.label, **judge_trust_kwargs(judge, choice), "judge_backend": g.label}


def build_scan_kwargs(
    mode: str, settings: Settings, backend: str | None = None, target_model: str | None = None, *,
    target_spec: str | None = None, grader_spec: str | None = None,
) -> dict:
    """Kwargs passed straight into `run_user_scan` for the resolved mode + backend (fail-closed)."""
    if mode == "demo":
        return {"demonstration": True}
    prefer = require_backend_allowed(backend, settings)
    if prefer == SPEC_BACKEND:
        return _spec_scan_kwargs(settings, target_spec, grader_spec)
    tm = _target_model(prefer, target_model, settings)
    target, judge, judge_model, choice = build_live_clients(
        tm, max_calls=settings.scan_max_calls, prefer=prefer
    )
    return {
        "demonstration": False,
        "judge_client": judge,
        "target_client": target,
        "target_model_id": tm,
        "judge_model": judge_model,
        **judge_trust_kwargs(judge, choice),
    }
