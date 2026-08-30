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
    "instruction_following": "Instruction following (quality)",
}


def _resolve_checks(checks: list[str] | None) -> list[str]:
    if not checks:
        # Default scan/audit to the SAFETY attack-suite checks; quality checks are opt-in by name.
        from fusion.judge.rubric import checks_of_kind

        return checks_of_kind("safety")
    unknown = [c for c in checks if c not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown checks: {unknown}; valid: {sorted(REGISTRY)}")
    return checks


def _owasp(check: str) -> str:
    t = get_rubric(check).owasp
    return f"{t.llm}/{t.asi}" if t.llm else ""


def list_checks() -> dict:
    """The checks Fusion can run, grouped by kind — 'safety' (OWASP-mapped adversarial risks) and
    'quality' (correctness / instruction-following) — with what good behavior means for each."""
    return {
        "checks": [
            {
                "id": c,
                "label": _CHECK_LABELS.get(c, c),
                "kind": get_rubric(c).kind,
                "owasp": _owasp(c),
                "intent": get_rubric(c).intent,
            }
            for c in sorted(REGISTRY)
        ]
    }


def _resolve_live_kwargs(live, target_model: str | None, backend: str | None) -> tuple[dict, str]:
    """Resolve scan kwargs + a mode label from the `live` setting.

    live ∈ {False,"off"} → demo; {True,"on"} → require a live backend (raise if none);
    "auto" → live if a backend is available, else fall back to demo. `backend`="ollama" (with a
    `target_model` like "llama3.2") audits an OPEN-WEIGHT agent locally, judged by Claude."""
    from fusion.integrations.live import LiveUnavailable

    tm = target_model or "claude-haiku-4-5"
    if live in (False, "off", None):
        return {"demonstration": True}, "demo"
    if live in (True, "on"):
        return build_live_scan_kwargs(target_model=tm, prefer=backend), "live"
    # "auto": try live, gracefully fall back to the labelled demo
    try:
        return build_live_scan_kwargs(target_model=tm, prefer=backend), "live"
    except LiveUnavailable:
        return {"demonstration": True}, "demo"


async def scan_prompt(
    system_prompt: str,
    checks: list[str] | None = None,
    tier: str = "quick",
    live=False,
    target_model: str | None = None,
    backend: str | None = None,
) -> dict:
    """FIND: grade a system prompt against the safety checks and list what got through.

    `live=False`/"off" runs the offline demonstration pipeline (no key, stamped demonstration=True).
    `live="auto"` uses a real backend when one is available (the Claude CLI subscription, an API key,
    or an Ollama open-weight target) and otherwise falls back to the labelled demo. `live=True`/"on"
    requires a live backend and raises `LiveUnavailable` if none. Set `backend="ollama"` +
    `target_model="llama3.2"` to audit an open-weight agent locally, judged by Claude (cross-family).
    Returns per-check grades, the baseline→hardened reduction, the honesty badge, and what landed.
    """
    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be non-empty")
    resolved = _resolve_checks(checks)
    # scan_prompt runs the SAFETY attack suite — quality checks have no attack probes and would crash
    # deep inside with an opaque FileNotFoundError. Reject them clearly and point to grade_quality.
    from fusion.judge.rubric import get_rubric

    non_safety = [c for c in resolved if get_rubric(c).kind != "safety"]
    if non_safety:
        raise ValueError(
            f"scan_prompt runs the safety attack suite; these are not safety checks: {non_safety}. "
            "Use grade_quality(...) (or audit_agent) for quality checks."
        )
    scan_tier = ScanTier.FULL if tier == "full" else ScanTier.QUICK
    scan_kwargs, _mode = _resolve_live_kwargs(live, target_model, backend)

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
        else ["No baseline issues detected."],
        "note": (
            "Demonstration numbers from an offline stand-in judge — the methodology is real; use "
            "live=\"auto\" (Claude CLI subscription or an Ollama open-weight target) for real numbers."
            if result.demonstration
            else "Live numbers from real models (baseline arm run through the target, judged by a real judge)."
        ),
    }


def _autonomy_config(autonomy: str) -> dict:
    """Map a single autonomy word to a runtime GuardConfig (the HITL decision-gate optionality).

    supervised → hold consequential/external/secret actions for human authorization (least-agency);
    autonomous → run unattended but still redact leaks. Pass this to check_output/check_tool_call."""
    if autonomy == "autonomous":
        return {
            "require_authorization": False,
            "on_external_action": "redact",
            "on_secret_output": "redact",
        }
    return {  # "supervised" (default, safest)
        "require_authorization": True,
        "on_external_action": "block",
        "on_secret_output": "block",
    }


def _plain_verdict(scan: dict) -> str:
    """A one-line, non-expert summary of a scan result."""
    failed = [c for c in scan["checks"] if (c.get("baseline_issue_rate") or 0) > 0]
    mode = "demo" if scan.get("demonstration") else "live"
    if not failed:
        return f"No safety issues found across {len(scan['checks'])} checks ({mode}). Overall grade {scan['overall_grade']}."
    worst = ", ".join(c["label"] for c in failed)
    return (
        f"Found issues in {len(failed)} of {len(scan['checks'])} checks ({mode}): {worst}. "
        f"Overall grade {scan['overall_grade']}. Apply the hardened prompt and runtime guardrail below."
    )


_GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "?": 5}


def _worst(grades: list[str]) -> str:
    return max(grades, key=lambda g: _GRADE_RANK.get(g, 5)) if grades else "?"


async def grade_quality(
    system_prompt: str,
    checks: list[str] | None = None,
    target_model: str | None = None,
    backend: str | None = None,
    concurrency: int = 6,
) -> dict:
    """Grade a real agent's QUALITY: run its prompt over normal test inputs on a LIVE target and judge
    each response. Requires a live backend (Claude CLI subscription or an Ollama open-weight target) —
    there is no 'demo' quality mode, because grading needs the agent's real outputs."""
    from fusion.integrations.live import build_live_clients
    from fusion.judge.rubric import checks_of_kind, get_rubric
    from fusion.measure.harness import measure_quality

    if checks:
        q_checks = [c for c in checks if get_rubric(c).kind == "quality"] or checks_of_kind("quality")
    else:
        q_checks = checks_of_kind("quality")
    tm = target_model or "claude-haiku-4-5"
    target, judge, judge_id, choice = build_live_clients(tm, prefer=backend)
    out = []
    for check in q_checks:
        res = await measure_quality(check, target, judge, system_prompt, target_model_id=tm, concurrency=concurrency)
        out.append({
            "check": check,
            "label": _CHECK_LABELS.get(check, check),
            "grade": res.grade,
            "issue_rate": round(res.issue_rate, 4),
            "n_defects": res.n_defects,
            "n": res.n,
            "defects": [{"input": d.user, "issue_type": d.issue_type, "excerpt": d.response_excerpt} for d in res.defects[:5]],
        })
    return {
        "overall_quality_grade": _worst([q["grade"] for q in out]),
        "judge": judge_id,
        "independence": choice.independence,
        "quality_checks": out,
    }


async def audit_agent(
    system_prompt: str,
    checks: list[str] | None = None,
    autonomy: str = "supervised",
    live="auto",
    target_model: str | None = None,
    backend: str | None = None,
    tier: str = "quick",
    dimensions: list[str] | None = None,
) -> dict:
    """One call = FIND + FIX + PROTECT across SAFETY and QUALITY.

    Runs the safety attack-scan and (when a live backend is available) grades the agent's quality on
    normal test inputs — both through the same calibrated judge. Returns a plain-language verdict, an
    overall grade (worst of safety + quality), per-check grades, the hardened prompt to paste back, the
    runtime-guardrail snippet, and the recommended runtime GuardConfig for your chosen `autonomy`
    (supervised = human-in-the-loop gates; autonomous = unattended + redact).

    Audit an OPEN-WEIGHT agent (where injection/exfil/agency attacks actually land) locally and free:
    `backend="ollama", target_model="llama3.2"` — judged by Claude (cross-family independence).
    `live="auto"` uses a real backend when available, else a labelled demo (quality needs a live backend).
    `dimensions` defaults to ["safety","quality"]; pass ["safety"] to skip quality grading.
    """
    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be non-empty")
    from fusion.judge.rubric import checks_of_kind, get_rubric

    dimensions = dimensions or ["safety", "quality"]
    resolved = _resolve_checks(checks)
    safety_checks = [c for c in resolved if get_rubric(c).kind == "safety"]
    # The fix + guardrail are always useful; scope them to the requested safety checks (or all safety).
    fix_checks = safety_checks or checks_of_kind("safety")

    result: dict = {
        "hardened_prompt": harden_prompt(system_prompt, fix_checks)["hardened_prompt"],
        "guardrail_snippet": guardrail_snippet(fix_checks)["snippet"],
        "autonomy": autonomy,
        "recommended_guard_config": _autonomy_config(autonomy),
    }
    grades: list[str] = []
    verdict_parts: list[str] = []
    mode = "demo"

    if "safety" in dimensions and safety_checks:
        scan = await scan_prompt(
            system_prompt, safety_checks, tier=tier, live=live, target_model=target_model, backend=backend
        )
        mode = "demo" if scan["demonstration"] else "live"
        result["safety"] = {"overall_grade": scan["overall_grade"], "checks": scan["checks"]}
        result["checks"] = scan["checks"]  # backward-compatible top-level safety checks
        result["note"] = scan["note"]
        grades.append(scan["overall_grade"])
        verdict_parts.append(_plain_verdict(scan))

    if "quality" in dimensions and live not in (False, "off", None):
        from fusion.integrations.live import LiveUnavailable

        try:
            quality = await grade_quality(system_prompt, checks, target_model, backend)
            result["quality"] = quality
            grades.append(quality["overall_quality_grade"])
            mode = "live"
            q_failed = [q["label"] for q in quality["quality_checks"] if q["grade"] not in ("A", "?")]
            if q_failed:
                verdict_parts.append(f"Quality issues in: {', '.join(q_failed)}.")
        except LiveUnavailable:
            result["quality"] = {"skipped": "quality grading needs a live backend (Claude CLI subscription or Ollama)"}

    result["overall_grade"] = _worst(grades) if grades else "?"
    result["mode"] = mode
    result["verdict"] = " ".join(verdict_parts) if verdict_parts else "No dimensions were run."
    return result


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
