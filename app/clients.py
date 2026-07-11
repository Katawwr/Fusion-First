"""Scan mode resolution and live-client assembly — the one place that decides demo vs real.

A `live` request without server keys fails closed (LiveUnavailable → 402); we NEVER silently serve
a demo card when a real one was asked for. All keys stay server-side; the frontend never sees them.
"""

from __future__ import annotations

from app.settings import Settings


class LiveUnavailable(Exception):
    """A real-model scan was requested but no server-side provider key is configured."""


def resolve_mode(requested: str | None, settings: Settings) -> str:
    if requested == "live":
        if not settings.has_live_keys:
            raise LiveUnavailable("real-model scans require a server-side API key")
        return "live"
    # None or "demo" → demo (the safe, keyless default).
    return "demo"


def build_scan_kwargs(mode: str, settings: Settings) -> dict:
    """Kwargs passed straight into `run_user_scan` for the resolved mode."""
    if mode == "demo":
        return {"demonstration": True}

    from fusion.model.providers.anthropic import AnthropicModelClient
    from fusion.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=settings.scan_max_calls)
    target = BudgetedModelClient(AnthropicModelClient(settings.anthropic_api_key), limits)

    if settings.openai_api_key:
        from fusion.model.providers.openai import OpenAIModelClient

        judge = BudgetedModelClient(OpenAIModelClient(settings.openai_api_key), limits)
        judge_model = "gpt-4o"  # cross-family judge (self-family guard)
    else:
        judge = BudgetedModelClient(AnthropicModelClient(settings.anthropic_api_key), limits)
        judge_model = "claude-sonnet-5"

    return {
        "demonstration": False,
        "judge_client": judge,
        "target_client": target,
        "target_model_id": settings.target_model,
        "judge_model": judge_model,
    }
