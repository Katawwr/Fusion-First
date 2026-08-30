"""Scan mode resolution and live-client assembly — the one place that decides demo vs real.

A `live` request without an available backend fails closed (LiveUnavailable → 402); we NEVER
silently serve a demo card when a real one was asked for. All keys stay server-side; the frontend
never sees them. Backends, in order of the operator's choosing (`backend` on the request):

  * "api"    — server-side ANTHROPIC/OPENAI keys (settings). The hosted default.
  * "cli"    — the server's `claude` CLI subscription (self-hosted / local dev, no key).
  * "ollama" — a local OPEN-WEIGHT target (Llama/Mistral/…), judged by Claude (cross-family). The
               product's focus: where injection/exfil/agency attacks actually land.
"""

from __future__ import annotations

from app.settings import Settings


class LiveUnavailable(Exception):
    """A real-model scan was requested but no server-side backend is available."""


def resolve_mode(requested: str | None, settings: Settings) -> str:
    # Availability is decided in build_scan_kwargs (which fails closed per backend), so a cli/ollama
    # backend can go live without server keys. "None"/"demo" stays the safe, keyless default.
    return "live" if requested == "live" else "demo"


def _budgeted(client, settings, *, enforce_allowlist=True):
    from fusion.security.budget import BudgetedModelClient, BudgetLimits

    return BudgetedModelClient(client, BudgetLimits(max_calls=settings.scan_max_calls), enforce_allowlist=enforce_allowlist)


def _claude_judge(settings: Settings, *, judge_model: str = "claude-sonnet-5"):
    """A Claude judge from a server-side key if present, else the server's `claude` CLI subscription.
    Raises LiveUnavailable if neither is available."""
    if settings.anthropic_api_key:
        from fusion.model.providers.anthropic import AnthropicModelClient

        return _budgeted(AnthropicModelClient(settings.anthropic_api_key, judge_model=judge_model), settings), judge_model
    from fusion.model.providers.claude_cli import ClaudeCliModelClient, claude_cli_available

    if claude_cli_available():
        return _budgeted(ClaudeCliModelClient(judge_model=judge_model), settings), judge_model
    raise LiveUnavailable("a Claude judge needs a server ANTHROPIC_API_KEY or the `claude` CLI")


def build_scan_kwargs(mode: str, settings: Settings, backend: str | None = None, target_model: str | None = None) -> dict:
    """Kwargs passed straight into `run_user_scan` for the resolved mode + backend (fail-closed)."""
    if mode == "demo":
        return {"demonstration": True}

    tm = target_model or settings.target_model

    if backend == "ollama":
        from fusion.model.providers.ollama import OllamaModelClient, ollama_available

        if not ollama_available():
            raise LiveUnavailable(
                "no Ollama server at localhost:11434 — run `ollama serve` and `ollama pull <model>`"
            )
        # Open-weight ids aren't on the Anthropic allowlist → don't enforce it for the target.
        target = _budgeted(OllamaModelClient(model=tm), settings, enforce_allowlist=False)
        judge, judge_model = _claude_judge(settings)  # cross-family (Claude judging an open model)
        return {"demonstration": False, "judge_client": judge, "target_client": target,
                "target_model_id": tm, "judge_model": judge_model}

    if backend == "cli":
        from fusion.model.providers.claude_cli import ClaudeCliModelClient, claude_cli_available

        if not claude_cli_available():
            raise LiveUnavailable("the `claude` CLI is not available on the server")
        target = _budgeted(ClaudeCliModelClient(), settings)
        judge, judge_model = _claude_judge(settings)
        return {"demonstration": False, "judge_client": judge, "target_client": target,
                "target_model_id": tm, "judge_model": judge_model}

    # default / "api": server-side keys.
    if not settings.has_live_keys:
        raise LiveUnavailable("real-model scans require a server-side API key (or backend=cli/ollama)")

    from fusion.model.providers.anthropic import AnthropicModelClient

    target = _budgeted(AnthropicModelClient(settings.anthropic_api_key), settings)
    if settings.openai_api_key:
        from fusion.model.providers.openai import OpenAIModelClient

        judge = _budgeted(OpenAIModelClient(settings.openai_api_key), settings)
        judge_model = "gpt-4o"  # cross-family judge (self-family guard)
    else:
        judge, judge_model = _claude_judge(settings)
    return {"demonstration": False, "judge_client": judge, "target_client": target,
            "target_model_id": tm, "judge_model": judge_model}
