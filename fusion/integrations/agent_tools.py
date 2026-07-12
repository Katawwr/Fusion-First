"""Fusion agent tools — the find / fix / protect loop, as plain functions.

These are the operations an AI coding agent (Claude Code, Cursor, an autonomous build agent) or a
CI job wants when it is building or shipping an AI agent:

  find     -> scan_prompt(system_prompt)        : grade the prompt, list what got through
  fix      -> harden_prompt(system_prompt)      : return the hardened prompt + guard block
  protect  -> guardrail_snippet()               : the runtime-guardrail code to drop in
  protect  -> check_output(text, ...)           : gate a model response at runtime
  protect  -> check_tool_call(name, args, ...)  : gate a tool call at runtime

Every function returns a JSON-serialisable dict (no pydantic objects leak out), so the same code
backs the MCP server, the CLI, and an HTTP layer. Offline and deterministic: `scan_prompt` runs the
keyless DEMONSTRATION pipeline (stamped `demonstration=True`); the runtime checks use the real,
model-free guardrail.
"""

from __future__ import annotations

from fusion.engine.fixes import apply_fix, guard_block
from fusion.engine.user_scan import run_user_scan
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import Decision, GuardConfig
from fusion.guardrail.snippet import guardrail_snippet as _snippet
from fusion.integrations.live import build_live_scan_kwargs
from fusion.judge.rubric import REGISTRY, get_rubric
from fusion.schemas import ScanEventType, ScanTier

# Plain-language names so a tool result reads well in an agent transcript.
_CHECK_LABELS = {
    "direct_prompt_injection": "Prompt injection / hijack",
    "excessive_agency": "Excessive agency (runaway actions)",
    "data_exfiltration": "Data exfiltration",
    "system_prompt_leakage": "System-prompt / secret leakage",
}


def _resolve_checks(checks: list[str] | None) -> list[str]:
    if not checks:
        return sorted(REGISTRY)
    unknown = [c for c in checks if c not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown checks: {unknown}; valid: {sorted(REGISTRY)}")
    return checks


def _owasp(check: str) -> str:
    t = get_rubric(check).owasp
    return f"{t.llm}/{t.asi}" if t.llm else ""


def list_checks() -> dict:
    """The safety checks Fusion can run, with their OWASP mapping and what 'safe' means."""
    return {
        "checks": [
            {
                "id": c,
                "label": _CHECK_LABELS.get(c, c),
                "owasp": _owasp(c),
                "intent": get_rubric(c).intent,
            }
            for c in sorted(REGISTRY)
        ]
    }


async def scan_prompt(
    system_prompt: str,
    checks: list[str] | None = None,
    tier: str = "quick",
    live: bool = False,
) -> dict:
    """FIND: grade a system prompt against the safety checks and list what got through.

    Default (`live=False`) runs the offline demonstration pipeline (no API key); every card is
    stamped `demonstration=True`. With `live=True` the prompt is run through a real model — this
    needs `ANTHROPIC_API_KEY` (and optionally `OPENAI_API_KEY` for a cross-family judge) in the
    environment and raises `LiveUnavailable` if it is missing. Returns per-check grades, the
    baseline→hardened issue-rate reduction, the honesty badge, and the concrete attacks that landed.
    """
    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be non-empty")
    resolved = _resolve_checks(checks)
    scan_tier = ScanTier.FULL if tier == "full" else ScanTier.QUICK
    scan_kwargs = build_live_scan_kwargs() if live else {"demonstration": True}

    result = None
    async for ev in run_user_scan(
        system_prompt=system_prompt,
        checks=resolved,
        tier=scan_tier,
        target_name="agent prompt",
        **scan_kwargs,
    ):
        if ev.type == ScanEventType.SCAN_COMPLETED and ev.result is not None:
            result = ev.result
    if result is None:
        raise RuntimeError("scan produced no result")

    landed_by_check: dict[str, list[str]] = {c: [] for c in resolved}
    for o in result.outcomes:
        if o.baseline_issue and o.check in landed_by_check:
            landed_by_check[o.check].append(o.attack_label)

    checks_out = []
    for card in result.cards:
        ba = card.before_after
        checks_out.append(
            {
                "check": card.check,
                "label": _CHECK_LABELS.get(card.check, card.check),
                "owasp": _owasp(card.check),
                "grade": card.grade,
                "baseline_issue_rate": round(ba.baseline_issue_rate, 4) if ba else None,
                "hardened_issue_rate": round(ba.hardened_issue_rate, 4) if ba else None,
                "reduction": round(ba.absolute_reduction.point, 4) if ba else None,
                "honesty": ba.honesty.value if ba else None,
                "attacks_that_landed": landed_by_check.get(card.check, []),
                "top_fix": card.top_fixes[0] if card.top_fixes else card.fix_title,
            }
        )

    any_issue = any((c["baseline_issue_rate"] or 0) > 0 for c in checks_out)
    return {
        "target": result.target_name,
        "overall_grade": result.overall_grade,
        "demonstration": result.demonstration,
        "checks": checks_out,
        "passed": not any_issue,
        "next_steps": [
            "Call harden_prompt(system_prompt) to get a fixed prompt you can paste back.",
            "Call guardrail_snippet() for runtime protection that holds even when the model slips.",
        ]
        if any_issue
        else ["No baseline issues detected in this demo scan."],
        "note": "Demonstration numbers from an offline stand-in judge — the methodology is real; "
        "supply an API key and re-record for live numbers.",
    }


def harden_prompt(system_prompt: str, checks: list[str] | None = None) -> dict:
    """FIX: return the system prompt with Fusion's tested guard rules appended (idempotent — it
    replaces its own block instead of stacking), plus the guard block on its own."""
    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be non-empty")
    resolved = _resolve_checks(checks)
    return {
        "hardened_prompt": apply_fix(system_prompt, resolved),
        "guard_block": guard_block(resolved),
        "checks": resolved,
    }


def guardrail_snippet(checks: list[str] | None = None) -> dict:
    """PROTECT: the copy-paste runtime-guardrail code (Python) for the given checks."""
    resolved = _resolve_checks(checks)
    return {"language": "python", "snippet": _snippet(resolved), "checks": resolved}


def _guard_from(
    allowlisted_domains: list[str] | None,
    secret_values: list[str] | None,
    system_prompt: str | None,
    require_authorization: bool,
    on_secret: str,
) -> Guardrail:
    return Guardrail(
        GuardConfig(
            allowlisted_domains=allowlisted_domains or [],
            secret_values=secret_values or [],
            system_prompt=system_prompt or "",
            require_authorization=require_authorization,
            on_secret_output=Decision.BLOCK if on_secret == "block" else Decision.REDACT,
        )
    )


def _events(outcome) -> list[dict]:
    return [{"check": e.check, "owasp": e.owasp, "decision": e.decision.value, "detail": e.detail} for e in outcome.events]


def check_output(
    text: str,
    secret_values: list[str] | None = None,
    system_prompt: str | None = None,
    on_secret: str = "redact",
) -> dict:
    """PROTECT (runtime): decide whether a model response is safe to return. Blocks/redacts leaked
    secrets, PII, and system-prompt reproductions. Returns the safe text to send instead."""
    guard = _guard_from(None, secret_values, system_prompt, False, on_secret)
    out = guard.guard_output(text)
    mitigated = out.decision != Decision.ALLOW
    return {
        "decision": out.decision.value,
        "safe": not mitigated,
        "safe_text": out.content,
        "findings": _events(out),
    }


def check_tool_call(
    name: str,
    arguments: dict,
    user_request: str = "",
    allowlisted_domains: list[str] | None = None,
    secret_values: list[str] | None = None,
    require_authorization: bool = True,
) -> dict:
    """PROTECT (runtime): decide whether a tool call is safe to execute. Blocks unauthorized
    consequential actions, sends to external/untrusted destinations, and secret/PII exfiltration."""
    guard = _guard_from(allowlisted_domains, secret_values, None, require_authorization, "block")
    out = guard.guard_tool_call(name, arguments or {}, user_request)
    return {
        "decision": out.decision.value,
        "allowed": not out.blocked,
        "blocked": out.blocked,
        "findings": _events(out),
    }
