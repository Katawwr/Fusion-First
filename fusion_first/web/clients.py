"""Demo vs live resolution and live-client assembly for the web app.

A live request without an available backend fails closed (LiveUnavailable -> 402), never a silent
demo card. Backend selection is shared with the CLI and MCP via `integrations.live`; metered
providers need FUSION_ALLOW_API_SPEND=1, and cmd:/python:/host stay CLI/MCP-only.
"""

from __future__ import annotations

import os

from fusion_first.integrations.live import LiveUnavailable, build_live_clients, judge_trust_kwargs
from fusion_first.web.settings import Settings

__all__ = ["LiveUnavailable", "build_scan_kwargs", "require_backend_allowed", "resolve_mode"]

DEFAULT_OLLAMA_MODEL = "llama3.2:1b"


def resolve_mode(requested: str | None, settings: Settings) -> str:
    # Availability is decided (fail-closed) in build_scan_kwargs.
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
    """Any model by spec, minus what a web page may not start: cmd:, python: and the host grader."""
    from fusion_first.backends.resolve import (
        OPAQUE_BACKENDS,
        BackendUnavailable,
        SpecError,
        build_grader_client,
        build_target_client,
        parse_grader,
        parse_target,
    )
    from fusion_first.model.registry import JudgeChoice
    from fusion_first.runs.engine import independence_of

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


def hosted_keys() -> list[str]:
    """Hosted providers whose key is set here (names only, never values)."""
    from fusion_first.backends.presets import ANTHROPIC_KEY_ENV, PROVIDERS

    envs = {name: env for name, (_, env) in PROVIDERS.items()} | {"anthropic": ANTHROPIC_KEY_ENV}
    return [name for name, env in envs.items() if os.environ.get(env)]


def web_graders(cli_ready: bool, ollama_models: list[str]) -> list[str]:
    """Built-in graders a web scan can run now, best first: the claude CLI, then pulled local graders
    whose pre-registered measurement met the policy floor."""
    from fusion_first.validate.prereg import LOCAL_GRADER_EVIDENCE, local_grader_status

    out = ["claude-cli"] if cli_ready else []
    for m in ollama_models:
        if m in LOCAL_GRADER_EVIDENCE and local_grader_status(m)["meets_floor"]:
            out.append(f"ollama-prob:{m}")
    return out


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
