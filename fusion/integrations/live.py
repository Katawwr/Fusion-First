"""Build the LIVE-mode clients for a real (non-demonstration) scan from environment keys.

Keys stay in the environment (never arguments passed around): `ANTHROPIC_API_KEY` is required to run
the user's prompt through a real target model; if `OPENAI_API_KEY` is also set it is used as a
cross-family judge (self-family guard), otherwise a Claude judge is used. Returns the exact kwargs
`run_user_scan` expects; raising `LiveUnavailable` when no key is present so callers can fail cleanly.
"""

from __future__ import annotations

import os


class LiveUnavailable(RuntimeError):
    """A live (real-model) scan was requested but no provider key is configured."""


def build_live_scan_kwargs(target_model: str = "claude-haiku-4-5", max_calls: int = 400) -> dict:
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise LiveUnavailable("live scans require ANTHROPIC_API_KEY in the environment")

    from fusion.model.providers.anthropic import AnthropicModelClient
    from fusion.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=max_calls)
    target = BudgetedModelClient(AnthropicModelClient(anthropic_key), limits)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        from fusion.model.providers.openai import OpenAIModelClient

        judge = BudgetedModelClient(OpenAIModelClient(openai_key), limits)
        judge_model = "gpt-4o"
    else:
        judge = BudgetedModelClient(AnthropicModelClient(anthropic_key), limits)
        judge_model = "claude-sonnet-5"

    return {
        "demonstration": False,
        "judge_client": judge,
        "target_client": target,
        "target_model_id": target_model,
        "judge_model": judge_model,
    }
