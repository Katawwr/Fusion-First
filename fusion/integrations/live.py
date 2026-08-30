"""Build the LIVE-mode clients for a real (non-demonstration) scan.

Selection order (subscription-first, so build/test needs no API key and spends no money):
  1. `FUSION_TARGET_BACKEND=cli`, or no `ANTHROPIC_API_KEY` but the `claude` CLI is on PATH →
     `ClaudeCliModelClient` (subscription auth). Judge = a stronger same-family tier (Sonnet vs a
     Haiku target) — independent enough and light on subscription usage.
  2. `ANTHROPIC_API_KEY` present → the SDK `AnthropicModelClient`; if `OPENAI_API_KEY` is also set it
     is used as a cross-family judge (self-family guard), else a Claude judge.
  3. Neither → raise `LiveUnavailable` so callers can fail cleanly.

Keys stay in the environment; nothing sensitive is passed around. `build_live_scan_kwargs` returns
exactly the kwargs `run_user_scan` accepts; `build_live_clients` also returns the `JudgeChoice` so the
measurement layer can disclose judge independence on the report card.
"""

from __future__ import annotations

import os

from fusion.model.registry import ModelRegistry


class LiveUnavailable(RuntimeError):
    """A live (real-model) scan was requested but no provider key or CLI backend is available."""


def _use_cli(prefer: str) -> bool:
    from fusion.model.providers.claude_cli import claude_cli_available

    if prefer == "cli":
        return True
    if prefer in ("api", "ollama"):
        return False
    # auto: only fall to the CLI when there is no API key (the CLI is the keyless path)
    return not os.environ.get("ANTHROPIC_API_KEY") and claude_cli_available()


def _build_claude_judge(limits, registry: ModelRegistry):
    """A Claude judge — the subscription CLI (no key) when available, else the API. Returns
    (judge_client, judge_model_id). Sonnet is the default tier (light + independent)."""
    from fusion.security.budget import BudgetedModelClient

    judge_id = registry.resolve("judge_primary")  # claude-sonnet-5
    if os.environ.get("ANTHROPIC_API_KEY"):
        from fusion.model.providers.anthropic import AnthropicModelClient

        return BudgetedModelClient(AnthropicModelClient(os.environ["ANTHROPIC_API_KEY"]), limits), judge_id
    from fusion.model.providers.claude_cli import ClaudeCliModelClient, claude_cli_available

    if not claude_cli_available():
        raise LiveUnavailable("a Claude judge needs ANTHROPIC_API_KEY or the `claude` CLI on PATH")
    return BudgetedModelClient(ClaudeCliModelClient(registry=registry, judge_model=judge_id), limits), judge_id


def build_live_clients(
    target_model: str = "claude-haiku-4-5",
    *,
    max_calls: int = 400,
    prefer: str | None = None,
):
    """Return (target_client, judge_client, judge_model_id, judge_choice) for a live scan.

    `prefer` ∈ {"auto","cli","api","ollama"}; defaults to env `FUSION_TARGET_BACKEND` then "auto".
    The `ollama` backend runs an OPEN-WEIGHT target locally (free, no key) judged by Claude — genuine
    cross-family independence, and the segment where injection/exfil/agency attacks actually land.
    """
    prefer = prefer or os.environ.get("FUSION_TARGET_BACKEND", "auto")
    from fusion.model.registry import JudgeChoice
    from fusion.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=max_calls)
    registry = ModelRegistry()

    if prefer == "ollama":
        from fusion.model.providers.ollama import OllamaModelClient, ollama_available

        if not ollama_available():
            raise LiveUnavailable(
                "Ollama target requested but no server answered at localhost:11434 — run "
                "`ollama serve` and `ollama pull <model>` (e.g. llama3.2)"
            )
        # Open-weight target ids aren't on the Anthropic allowlist → don't enforce it for the target.
        target = BudgetedModelClient(
            OllamaModelClient(model=target_model), limits, enforce_allowlist=False
        )
        judge, judge_id = _build_claude_judge(limits, registry)
        choice = JudgeChoice(
            judge_id,
            "cross_family",
            f"Independent judge: {judge_id} (Anthropic) evaluating an open-weight target "
            f"({target_model}) — a different model family, the strongest independence tier.",
        )
        return target, judge, judge_id, choice

    if _use_cli(prefer):
        from fusion.model.providers.claude_cli import ClaudeCliModelClient, claude_cli_available

        if not claude_cli_available():
            raise LiveUnavailable("CLI backend requested but the `claude` binary was not found")
        # No cross-family judge over the CLI (it cannot serve OpenAI) → same-family cross-tier.
        choice = registry.choose_judge_with_disclosure(target_model, cross_family_available=False)
        target = BudgetedModelClient(ClaudeCliModelClient(registry=registry), limits)
        judge = BudgetedModelClient(
            ClaudeCliModelClient(registry=registry, judge_model=choice.judge_id), limits
        )
        return target, judge, choice.judge_id, choice

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise LiveUnavailable(
            "live scans require ANTHROPIC_API_KEY, the `claude` CLI, or an Ollama target"
        )
    from fusion.model.providers.anthropic import AnthropicModelClient

    target = BudgetedModelClient(AnthropicModelClient(anthropic_key), limits)
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        from fusion.model.providers.openai import OpenAIModelClient

        choice = registry.choose_judge_with_disclosure(target_model, cross_family_available=True)
        judge = BudgetedModelClient(OpenAIModelClient(openai_key), limits)
        return target, judge, choice.judge_id, choice

    # Same-family cross-tier: the disclosed (stronger) judge tier must ACTUALLY run, so pass it as the
    # judge_model override — otherwise we'd disclose Opus while the SDK judged with the Sonnet default.
    choice = registry.choose_judge_with_disclosure(target_model, cross_family_available=False)
    judge = BudgetedModelClient(
        AnthropicModelClient(anthropic_key, judge_model=choice.judge_id), limits
    )
    return target, judge, choice.judge_id, choice


def build_live_scan_kwargs(
    target_model: str = "claude-haiku-4-5", max_calls: int = 400, prefer: str | None = None
) -> dict:
    """The kwargs `run_user_scan` expects for a live scan (subscription CLI, API, or Ollama)."""
    target, judge, judge_model, _choice = build_live_clients(
        target_model, max_calls=max_calls, prefer=prefer
    )
    return {
        "demonstration": False,
        "judge_client": judge,
        "target_client": target,
        "target_model_id": target_model,
        "judge_model": judge_model,
    }
