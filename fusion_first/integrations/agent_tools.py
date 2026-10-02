"""Agent tools (scan, audit, guard, optional prompt fix) as plain functions returning JSON-serialisable
dicts; they back the MCP server, the CLI and the web API."""

from __future__ import annotations

from fusion_first.engine.fixes import apply_fix, guard_block
from fusion_first.engine.guard_replay import in_sample_payload as _guard_in_sample
from fusion_first.engine.user_scan import run_user_scan
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import Decision, GuardConfig
from fusion_first.guardrail.snippet import guardrail_snippet as _snippet
from fusion_first.integrations.live import build_live_scan_kwargs
from fusion_first.judge.rubric import REGISTRY, checks_of_kind, get_rubric
from fusion_first.schemas import ScanEventType, ScanTier

_CHECK_LABELS = {
    "direct_prompt_injection": "Prompt injection / hijack",
    "excessive_agency": "Excessive agency (runaway actions)",
    "data_exfiltration": "Data exfiltration",
    "system_prompt_leakage": "System-prompt / secret leakage",
    "instruction_following": "Instruction following (quality)",
}


def _resolve_checks(checks: list[str] | None) -> list[str]:
    if not checks:
        return checks_of_kind("safety")  # quality checks are opt-in by name
    unknown = [c for c in checks if c not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown checks: {unknown}; valid: {sorted(REGISTRY)}")
    return checks


def _owasp(check: str) -> str:
    t = get_rubric(check).owasp
    return f"{t.llm}/{t.asi}" if t.llm else ""


def list_checks() -> dict:
    """The checks Fusion can run, with their kind, OWASP mapping and intent."""
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
    """(scan kwargs, mode): off -> demo; on -> live or raise; "auto" -> live if available, else demo."""
    from fusion_first.integrations.live import LiveUnavailable

    tm = target_model or "claude-haiku-4-5"
    if live in (False, "off", None):
        return {"demonstration": True}, "demo"
    if live in (True, "on"):
        return build_live_scan_kwargs(target_model=tm, prefer=backend), "live"
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
    """Grade a system prompt against the safety checks and list the attacks that got through.

    `live`: False/"off" runs the stamped offline demonstration, "auto" uses a live backend when one is
    available, True/"on" requires one (LiveUnavailable otherwise)."""
    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be non-empty")
    resolved = _resolve_checks(checks)
    # Quality checks have no attack probes; reject them here rather than fail deep inside.
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
                "n_pairs": ba.n_pairs if ba else 0,
                "baseline_issue_rate": round(ba.baseline_issue_rate, 4) if ba else None,
                "hardened_issue_rate": round(ba.hardened_issue_rate, 4) if ba else None,
                "reduction": round(ba.absolute_reduction.point, 4) if ba else None,
                "honesty": ba.honesty.value if ba else None,
                "attacks_that_landed": landed_by_check.get(card.check, []),
                "top_fix": card.top_fixes[0] if card.top_fixes else card.fix_title,
            }
        )

    any_issue = any((c["baseline_issue_rate"] or 0) > 0 for c in checks_out)
    unmeasured = any(c["grade"] == "?" for c in checks_out)
    return {
        "target": result.target_name,
        "overall_grade": result.overall_grade,
        "demonstration": result.demonstration,
        "checks": checks_out,
        "passed": not any_issue and not unmeasured,
        "guard_in_sample": _guard_in_sample(result.outcomes, result.cards),  # live scans only
        "next_steps": [
            ("Add the runtime guardrail: guardrail_snippet() for the code, or check_output / check_tool_call "
            "per reply and per tool call."),
            ("Optional: harden_prompt(system_prompt) appends the prompt fix; re-test it on your model "
            "(on small open-weight models it rarely cut attacks and raised refusals of safe requests)."),
        ]
        if any_issue
        else ["No baseline issues detected."],
        "note": (
            "Demonstration numbers from an offline stand-in judge: the methodology is real; use "
            "live=\"auto\" (Claude CLI subscription or an Ollama open-weight target) for real numbers."
            if result.demonstration
            else "Live numbers from real models (baseline arm run through the target, judged by a real judge)."
        ),
    }


def _autonomy_config(autonomy: str) -> dict:
    """Runtime GuardConfig for an autonomy level: supervised holds actions for the user, autonomous redacts."""
    if autonomy == "autonomous":
        return {
            "require_authorization": False,
            "on_external_action": "redact",
            "on_secret_output": "redact",
        }
    return {  # "supervised" (default)
        "require_authorization": True,
        "on_external_action": "block",
        "on_secret_output": "block",
    }


def _plain_verdict(scan: dict) -> str:
    failed = [c for c in scan["checks"] if (c.get("baseline_issue_rate") or 0) > 0]
    mode = "demo" if scan.get("demonstration") else "live"
    if not failed:
        return f"No safety issues found across {len(scan['checks'])} checks ({mode}). Overall grade {scan['overall_grade']}."
    worst = ", ".join(c["label"] for c in failed)
    return (
        f"Found issues in {len(failed)} of {len(scan['checks'])} checks ({mode}): {worst}. "
        f"Overall grade {scan['overall_grade']}. Add the runtime guardrail below; the prompt fix is optional "
        f"(re-test it on your model)."
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
    """Run the prompt over normal test inputs on a live target and judge each response (no demo mode)."""
    from fusion_first.integrations.live import build_live_clients
    from fusion_first.measure.harness import measure_quality

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
    """Safety scan plus (with a live backend) quality grading, the guardrail snippet, the runtime config
    for `autonomy` and the optional hardened prompt; the overall grade is the worst of both."""
    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be non-empty")
    dimensions = dimensions or ["safety", "quality"]
    resolved = _resolve_checks(checks)
    safety_checks = [c for c in resolved if get_rubric(c).kind == "safety"]
    fix_checks = safety_checks or checks_of_kind("safety")

    result: dict = {
        "guardrail_snippet": guardrail_snippet(fix_checks)["snippet"],
        "hardened_prompt": harden_prompt(system_prompt, fix_checks)["hardened_prompt"],
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
        result["checks"] = scan["checks"]
        result["note"] = scan["note"]
        grades.append(scan["overall_grade"])
        verdict_parts.append(_plain_verdict(scan))

    if "quality" in dimensions and live not in (False, "off", None):
        from fusion_first.integrations.live import LiveUnavailable

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
    """The prompt with Fusion's fix block appended idempotently, plus the block on its own (optional:
    on small open-weight models it rarely cut attacks and raised refusals)."""
    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be non-empty")
    resolved = _resolve_checks(checks)
    return {
        "hardened_prompt": apply_fix(system_prompt, resolved),
        "guard_block": guard_block(resolved),
        "checks": resolved,
    }


def guardrail_snippet(checks: list[str] | None = None) -> dict:
    """The copy-paste runtime-guardrail code (Python) for the given checks."""
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
    """Gate a model response: block/redact leaked secrets, PII and system-prompt reproductions."""
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
    untrusted_context: bool = False,
    untrusted_text: str = "",
) -> dict:
    """Gate a tool call against the user's own request, external destinations and exfiltration.

    untrusted_context: tool results or documents are in the conversation (unrequested private reads
    are blocked); untrusted_text: their text (a read it asks for alongside an outside send is blocked).
    user_request must be the user's own words, never text from a tool result."""
    guard = _guard_from(allowlisted_domains, secret_values, None, require_authorization, "block")
    out = guard.guard_tool_call(name, arguments or {}, user_request, untrusted_context=untrusted_context,
                                untrusted_text=untrusted_text if isinstance(untrusted_text, str) else "")
    return {
        "decision": out.decision.value,
        "allowed": not out.blocked,
        "blocked": out.blocked,
        "findings": _events(out),
    }
