"""Live (real-model) clients for a scan, zero-spend by default.

`cli`/`auto` use the `claude` CLI on subscription auth; `ollama` runs a local open-weight target
judged by Claude over the CLI; `api` (metered) needs both `prefer="api"` and FUSION_ALLOW_API_SPEND=1,
so an ambient API key is never used. Without a permitted backend, `LiveUnavailable` is raised.
"""

from __future__ import annotations

import os

from fusion_first.model.registry import ModelRegistry

METERED_OPT_IN_ENV = "FUSION_ALLOW_API_SPEND"


class LiveUnavailable(RuntimeError):
    """A live (real-model) scan was requested but no permitted backend is available."""


def metered_allowed(prefer: str) -> bool:
    """Metered API use needs BOTH an explicit `api` backend choice and the opt-in env switch."""
    return prefer == "api" and os.environ.get(METERED_OPT_IN_ENV) == "1"


def _cli_judge(limits, registry: ModelRegistry, judge_id: str):
    from fusion_first.model.providers.claude_cli import ClaudeCliModelClient
    from fusion_first.security.budget import BudgetedModelClient

    _require_cli("grading uses Claude through the `claude` CLI (subscription)")
    return BudgetedModelClient(ClaudeCliModelClient(registry=registry, judge_model=judge_id), limits)


def _require_cli(purpose: str) -> None:
    """Refuse before anything runs (never after the target answered) unless the CLI can make calls."""
    from fusion_first.model.providers import claude_cli

    ready, reason = claude_cli.claude_cli_ready()
    if not ready:
        raise LiveUnavailable(
            f"{purpose}, and it can't run here: {reason}. Metered API keys are never used unless you "
            f"pass --backend api and set {METERED_OPT_IN_ENV}=1"
        )


def build_live_clients(
    target_model: str = "claude-haiku-4-5",
    *,
    max_calls: int = 400,
    prefer: str | None = None,
):
    """(target_client, judge_client, judge_model_id, judge_choice); `prefer` defaults to
    FUSION_TARGET_BACKEND, then "auto"."""
    prefer = prefer or os.environ.get("FUSION_TARGET_BACKEND", "auto")
    from fusion_first.model.registry import JudgeChoice
    from fusion_first.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=max_calls)
    registry = ModelRegistry()

    if prefer == "ollama":
        from fusion_first.model.providers.ollama import OllamaModelClient, ollama_available

        if not ollama_available():
            raise LiveUnavailable(
                "Ollama target requested but no server answered at 127.0.0.1:11434: run "
                "`ollama serve` and `ollama pull <model>` (e.g. llama3.2:1b)"
            )
        # Open-weight target ids aren't on the Anthropic allowlist.
        target = BudgetedModelClient(
            OllamaModelClient(model=target_model), limits, enforce_allowlist=False
        )
        judge_id = registry.resolve("judge_primary")
        judge = _cli_judge(limits, registry, judge_id)
        choice = JudgeChoice(
            judge_id,
            "cross_family",
            f"Independent judge: {judge_id} (Anthropic) evaluating an open-weight target "
            f"({target_model}): a different model family, the strongest independence tier.",
        )
        return target, judge, judge_id, choice

    if prefer in ("auto", "cli"):
        from fusion_first.model.providers.claude_cli import ClaudeCliModelClient

        _require_cli("this live backend runs Claude through the `claude` CLI (subscription); "
                     "or use --backend ollama with a local model")
        # The CLI cannot serve another family, so the judge is same-family cross-tier.
        choice = registry.choose_judge_with_disclosure(target_model, cross_family_available=False)
        target = BudgetedModelClient(ClaudeCliModelClient(registry=registry), limits)
        judge = BudgetedModelClient(
            ClaudeCliModelClient(registry=registry, judge_model=choice.judge_id), limits
        )
        return target, judge, choice.judge_id, choice

    if prefer != "api":
        raise LiveUnavailable(f"unknown backend '{prefer}' (use auto, cli, ollama, or api)")

    if not metered_allowed(prefer):
        raise LiveUnavailable(
            f"--backend api uses METERED API keys and is disabled by default; set "
            f"{METERED_OPT_IN_ENV}=1 to allow spending on your own key"
        )
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise LiveUnavailable("--backend api needs ANTHROPIC_API_KEY")
    from fusion_first.model.providers.anthropic import AnthropicModelClient

    target = BudgetedModelClient(AnthropicModelClient(anthropic_key), limits)
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        from fusion_first.model.providers.openai import OpenAIModelClient

        choice = registry.choose_judge_with_disclosure(target_model, cross_family_available=True)
        judge = BudgetedModelClient(OpenAIModelClient(openai_key), limits)
        return target, judge, choice.judge_id, choice

    # The disclosed (stronger) judge tier must actually run, so pass it as the judge_model override.
    choice = registry.choose_judge_with_disclosure(target_model, cross_family_available=False)
    judge = BudgetedModelClient(
        AnthropicModelClient(anthropic_key, judge_model=choice.judge_id), limits
    )
    return target, judge, choice.judge_id, choice


def build_live_scan_kwargs(
    target_model: str = "claude-haiku-4-5", max_calls: int = 400, prefer: str | None = None
) -> dict:
    """The kwargs `run_user_scan` expects for a live scan."""
    target, judge, judge_model, choice = build_live_clients(
        target_model, max_calls=max_calls, prefer=prefer
    )
    return {
        "demonstration": False,
        "judge_client": judge,
        "target_client": target,
        "target_model_id": target_model,
        "judge_model": judge_model,
        **judge_trust_kwargs(judge, choice),
    }


def judge_trust_kwargs(judge_client, choice) -> dict:
    """Judge disclosure for the card: backend, independence, and whether sampling is pinned (the CLI
    can't set temperature)."""
    inner = getattr(judge_client, "inner", judge_client)
    name = type(inner).__name__
    backend = {
        "ClaudeCliModelClient": "claude_cli",
        "AnthropicModelClient": "api_anthropic",
        "OpenAIModelClient": "api_openai",
        "OllamaModelClient": "ollama",
    }.get(name, name)
    return {
        "judge_choice": choice,
        "judge_backend": backend,
        "sampling_pinned": bool(getattr(inner, "controls_sampling", True)),
    }
