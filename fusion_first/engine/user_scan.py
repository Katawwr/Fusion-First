"""User-prompt scan: run each check's attacks against the prompt as pasted (baseline) and hardened, judge
both arms, and stream `ScanEvent`s.

DEMO uses the templates' canned responses (the prompt is NOT run) and the offline heuristic judge;
cards are stamped `demonstration=True`. LIVE runs a real target and judge.

Contract: the hardened arm is exactly the prompt the user copies (`apply_fix` computed once); one failed
attack is UNSCORED and counted, run-level failures stop the scan with an ERROR event; a circuit breaker
stops a backend that keeps failing; every stream ends with exactly one SCAN_COMPLETED or ERROR event.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from fusion_first.attacks.taxonomy import Crosswalk
from fusion_first.attacks.templates import AttackTemplate, select_templates
from fusion_first.engine import guard_replay
from fusion_first.engine.fixes import apply_fix
from fusion_first.engine.report import build_report_card
from fusion_first.errors import ErrorKind, classify, isolatable
from fusion_first.judge.judge import Judge
from fusion_first.judge.rubric import get_rubric
from fusion_first.measure.harness import load_quality_tests
from fusion_first.model.client import ModelClient, ModelRequest, ModelRole
from fusion_first.model.replay import Cassette, CassetteMiss, ReplayModelClient
from fusion_first.recording import CASSETTE_DIR, build_trajectory_cassette
from fusion_first.schemas import (
    AccuracyResult,
    ProbeOutcome,
    ScanEvent,
    ScanEventType,
    ScanResult,
    ScanTier,
    Trajectory,
    TrustInfo,
    Verdict,
)
from fusion_first.stats.calibration import run_calibration
from fusion_first.stats.paired import before_after

log = logging.getLogger(__name__)

DEMO_JUDGE_MODEL = "demo-heuristic-judge"
_GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "?": 5}

# (accuracy, gold_version, note, source) for a check + judge id.
AccuracyProvider = Callable[[str, str], Awaitable[tuple[AccuracyResult | None, str, str, str]]]


def _worst_grade(grades: list[str]) -> str:
    return max(grades, key=lambda g: _GRADE_RANK.get(g, 5)) if grades else "?"


class ScanAbort(Exception):
    """Stop the scan with an ERROR event carrying `code` and a user-safe message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ErrorBreaker:
    """Trips on `max_consecutive` errors in a row, or an error rate above `max_error_rate` once at
    least `min_seen` attacks have finished."""

    max_consecutive: int = 5
    max_error_rate: float = 0.5
    min_seen: int = 8
    seen: int = 0
    errors: int = 0
    consecutive: int = 0

    def record(self, ok: bool) -> bool:
        """Record one finished attack; True if the breaker has tripped."""
        self.seen += 1
        if ok:
            self.consecutive = 0
        else:
            self.errors += 1
            self.consecutive += 1
        if self.consecutive >= self.max_consecutive:
            return True
        return self.seen >= self.min_seen and self.errors / self.seen > self.max_error_rate


def _excerpt(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _evidence(verdict: Verdict) -> str:
    for c in verdict.criteria:
        if c.violated and c.evidence:
            return _excerpt(c.evidence, 240)
    return ""


def _last_assistant_text(traj: Trajectory) -> str:
    for step in reversed(traj.steps):
        if step.role.value == "assistant" and step.content:
            return step.content
    return ""


async def _target_response(
    template: AttackTemplate, system_prompt: str, target_client: ModelClient, target_model_id: str
) -> str:
    req = ModelRequest(
        role=ModelRole.TARGET,
        system=system_prompt,
        messages=template.target_messages(),
        max_tokens=800,
        model_id=target_model_id,
    )
    resp = await target_client.complete(req)
    return resp.text


async def _build_arms(
    template: AttackTemplate,
    system_prompt: str,
    hardened_prompt: str,
    *,
    demonstration: bool,
    target_client: ModelClient | None,
    target_model_id: str | None,
) -> tuple[Trajectory, Trajectory]:
    if demonstration:
        return (
            template.demo_trajectory(system_prompt, hardened=False),
            template.demo_trajectory(hardened_prompt, hardened=True),
        )
    if target_client is None or target_model_id is None:
        raise ValueError("live scan requires a target_client and target_model_id")
    base_text = await _target_response(template, system_prompt, target_client, target_model_id)
    hard_text = await _target_response(template, hardened_prompt, target_client, target_model_id)
    return (
        template.live_trajectory(system_prompt, base_text),
        template.live_trajectory(hardened_prompt, hard_text),
    )


def _demo_judge(trajectories: list[Trajectory], check: str) -> Judge:
    cassette = build_trajectory_cassette(trajectories, check)
    return Judge(ReplayModelClient(cassette, strict=True))


def _unscored(template: AttackTemplate, check: str, exc: BaseException, stage: str) -> ProbeOutcome:
    base = dict(check=check, probe_id=template.id, attack_label=template.attack_label, owasp=template.owasp)
    return _unscored_named(base, exc, stage)


async def _score_template(
    template: AttackTemplate,
    check: str,
    system_prompt: str,
    hardened_prompt: str,
    judge: Judge,
    *,
    demonstration: bool,
    target_client: ModelClient | None,
    target_model_id: str | None,
    arms: tuple[Trajectory, Trajectory] | None = None,
) -> ProbeOutcome:
    """Run one attack on both arms and judge them. Isolatable failures become UNSCORED; run-level ones
    propagate."""
    rubric = get_rubric(check)
    try:
        base_traj, hard_traj = arms or await _build_arms(
            template, system_prompt, hardened_prompt,
            demonstration=demonstration, target_client=target_client, target_model_id=target_model_id,
        )
    except Exception as exc:  # noqa: BLE001
        if isolatable(exc):
            return _unscored(template, check, exc, "target")
        raise
    try:
        b: Verdict = await judge.evaluate(base_traj, rubric)
        h: Verdict = await judge.evaluate(hard_traj, rubric)
    except Exception as exc:  # noqa: BLE001
        if isolatable(exc):
            return _unscored(template, check, exc, "judge")
        raise
    verdict, leak = (None, None) if demonstration else _replay(template, base_traj, system_prompt)
    return ProbeOutcome(
        check=check,
        probe_id=template.id,
        attack_label=template.attack_label,
        owasp=template.owasp,
        baseline_issue=b.is_issue,
        hardened_issue=h.is_issue,
        baseline_severity=b.severity,
        hardened_severity=h.severity,
        evidence=_evidence(b) if b.is_issue else "",
        baseline_excerpt=_excerpt(_last_assistant_text(base_traj), 200),
        guard_replay=verdict,
        guard_leak=leak,
    )


def _replay(template: AttackTemplate, trajectory: Trajectory, system_prompt: str) -> tuple[str | None, bool | None]:
    """The in-sample guard verdict for a live reply, and whether a stop was a leak it caught. Demos get
    none (canned replies were not written for this prompt); a guard error costs the verdict, not the scan."""
    try:
        guard = guard_replay.guard_for_prompt(system_prompt)
        verdict = guard_replay.guard_verdict(template, trajectory, guard)
        return verdict, verdict == "stopped" and guard_replay.reply_leaks(trajectory, guard)
    except Exception:  # noqa: BLE001  the replay is a diagnostic; the scan must still finish
        log.warning("guard replay failed for %s", template.id, exc_info=True)
        return None, None


async def _plain_response(
    user: str, system_prompt: str, target_client: ModelClient, target_model_id: str
) -> str:
    req = ModelRequest(
        role=ModelRole.TARGET,
        system=system_prompt,
        messages=[{"role": "user", "content": user}],
        max_tokens=600,
        model_id=target_model_id,
    )
    return (await target_client.complete(req)).text


def _verify(spec: dict, prompt: str, response: str) -> tuple[bool | None, str]:
    """IFEval-style deterministic grading: (is_defect, or None if undecidable; evidence)."""
    from fusion_first.validate import ifeval_lite

    row = {"prompt": prompt, "instruction_id_list": spec["instruction_id_list"], "kwargs": spec["kwargs"]}
    res = ifeval_lite.evaluate_prompt(row, response)
    if res["all_followed"] is None:
        return None, "the verifier could not decide"
    failed = [k for k, v in res["per_instruction"].items() if v is False]
    if failed:
        return True, "verifier: instruction not followed: " + ", ".join(sorted(set(failed)))
    return False, "verifier: every instruction followed"


async def _score_quality_test(
    test: dict,
    check: str,
    system_prompt: str,
    hardened_prompt: str,
    judge: Judge,
    *,
    target_client: ModelClient | None,
    target_model_id: str | None,
) -> ProbeOutcome:
    """Run one quality test on both arms, graded by its verifier when it has one, else the judge. The
    before/after is a fix-COST measure: did the safety fix hurt quality?"""
    from fusion_first.attacks.agentic import build_agentic_trajectory
    from fusion_first.errors import JudgeUndecided

    rubric = get_rubric(check)
    label = test["user"] if len(test["user"]) <= 140 else test["user"][:139] + "…"
    base = dict(check=check, probe_id=test["id"], attack_label=label, owasp=rubric.owasp)
    if target_client is None or target_model_id is None:
        raise ValueError("quality tests need a live target model")
    try:
        base_text = await _plain_response(test["user"], system_prompt, target_client, target_model_id)
        hard_text = await _plain_response(test["user"], hardened_prompt, target_client, target_model_id)
    except Exception as exc:  # noqa: BLE001
        if isolatable(exc):
            return _unscored_named(base, exc, "target")
        raise
    spec = test.get("verify")
    if spec:
        b_issue, b_ev = _verify(spec, test["user"], base_text)
        h_issue, _ = _verify(spec, test["user"], hard_text)
        if b_issue is None or h_issue is None:
            return _unscored_named(base, JudgeUndecided("verifier undecidable"), "judge")
        return ProbeOutcome(
            **base, baseline_issue=b_issue, hardened_issue=h_issue,
            evidence=b_ev if b_issue else "", baseline_excerpt=_excerpt(base_text, 200),
        )
    try:
        b = await judge.evaluate(build_agentic_trajectory(system_prompt, test["user"], base_text), rubric)
        h = await judge.evaluate(build_agentic_trajectory(hardened_prompt, test["user"], hard_text), rubric)
    except Exception as exc:  # noqa: BLE001
        if isolatable(exc):
            return _unscored_named(base, exc, "judge")
        raise
    return ProbeOutcome(
        **base, baseline_issue=b.is_issue, hardened_issue=h.is_issue,
        baseline_severity=b.severity, hardened_severity=h.severity,
        evidence=_evidence(b) if b.is_issue else "", baseline_excerpt=_excerpt(base_text, 200),
    )


def _unscored_named(base: dict, exc: BaseException, stage: str) -> ProbeOutcome:
    return ProbeOutcome(
        **base, baseline_issue=None, hardened_issue=None,
        error=_excerpt(f"{stage} failed: {type(exc).__name__}: {exc}", 240),
        error_kind=classify(exc, stage).value,
    )


_ABORT_MESSAGES = {
    "budget_exceeded": "The scan hit its model-call budget before finishing.",
    "quota_exhausted": "The Claude subscription usage limit was reached; the scan stopped "
    "(nothing is retried into overage). Try again after the limit resets.",
    "model_not_allowed": "A model outside the allowlist was requested.",
    "auth_refused": "The claude CLI is not on subscription auth (or not logged in); no calls were "
    "made. Run `claude auth login` with your Claude subscription account.",
    "prompt_too_long": "The prompt is too long for this backend.",
    "internal": "The scan failed unexpectedly.",
}


def _abort_for(exc: BaseException) -> ScanAbort:
    code = {
        ErrorKind.BUDGET_EXCEEDED: "budget_exceeded",
        ErrorKind.QUOTA_EXHAUSTED: "quota_exhausted",
        ErrorKind.MODEL_NOT_ALLOWED: "model_not_allowed",
        ErrorKind.AUTH_REFUSED: "auth_refused",
        ErrorKind.PROMPT_TOO_LONG: "prompt_too_long",
    }.get(classify(exc), "internal")
    return ScanAbort(code, _ABORT_MESSAGES[code])


async def run_user_scan(
    *,
    system_prompt: str,
    checks: list[str],
    tier: ScanTier = ScanTier.QUICK,
    demonstration: bool = True,
    judge_client: ModelClient | None = None,
    target_client: ModelClient | None = None,
    target_model_id: str | None = None,
    target_name: str = "Your prompt",
    judge_model: str | None = None,
    version: str = "v1",
    hardened_prompt: str | None = None,
    concurrency: int = 3,
    judge_choice=None,
    judge_backend: str | None = None,
    sampling_pinned: bool | None = None,
    judge_accuracy_provider: AccuracyProvider | None = None,
    breaker: ErrorBreaker | None = None,
) -> AsyncIterator[ScanEvent]:
    if not demonstration and judge_client is None:
        raise ValueError("live scan requires a judge_client")
    judge_model = judge_model or (DEMO_JUDGE_MODEL if demonstration else "judge")
    crosswalk_version = Crosswalk().code_version()
    hardened = hardened_prompt if hardened_prompt is not None else apply_fix(system_prompt, checks)
    hardened_sha = hashlib.sha256(hardened.encode("utf-8")).hexdigest()
    execution = "canned" if demonstration else "live"
    breaker = breaker or ErrorBreaker()
    accuracy_for: AccuracyProvider = judge_accuracy_provider or (
        _demo_accuracy if demonstration else _live_accuracy_unmeasured
    )

    kinds = {check: get_rubric(check).kind for check in checks}
    if demonstration and any(k == "quality" for k in kinds.values()):
        raise ValueError(
            "quality checks need a live model: demonstration responses are canned and would say "
            "nothing about your agent's quality"
        )
    plan: dict[str, list] = {
        check: (
            load_quality_tests(check, version) if kinds[check] == "quality"
            else select_templates(check, tier, version)
        )
        for check in checks
    }
    total = sum(len(v) for v in plan.values())
    yield ScanEvent(
        type=ScanEventType.SCAN_STARTED,
        total=total,
        demonstration=demonstration,
        message=f"Building a {tier.value} attack suite ({total} attacks across {len(checks)} checks)…",
    )

    cards = []
    outcomes: list[ProbeOutcome] = []
    completed = 0
    try:
        for check in checks:
            templates = plan[check]
            is_quality = kinds[check] == "quality"
            yield ScanEvent(
                type=ScanEventType.CHECK_STARTED,
                check=check,
                total=len(templates),
                demonstration=demonstration,
                message=(
                    f"Grading quality: {check.replace('_', ' ')}" if is_quality
                    else f"Attacking your prompt: {check.replace('_', ' ')}"
                ),
            )

            check_outcomes: dict[str, ProbeOutcome] = {}
            if demonstration:
                # Canned arms are deterministic; seed one replay judge over all of them.
                arms = {
                    t.id: (t.demo_trajectory(system_prompt, hardened=False),
                           t.demo_trajectory(hardened, hardened=True))
                    for t in templates
                }
                demo_judge = _demo_judge([tr for pair in arms.values() for tr in pair], check)
                for t in templates:
                    outcome = await _score_template(
                        t, check, system_prompt, hardened, demo_judge,
                        demonstration=True, target_client=None, target_model_id=None,
                        arms=arms[t.id],
                    )
                    check_outcomes[t.id] = outcome
                    completed += 1
                    yield _probe_event(check, outcome, completed, total, demonstration)
            else:
                live_judge = Judge(judge_client)
                sem = asyncio.Semaphore(max(1, concurrency))

                async def one(
                    t, check: str = check, sem=sem, judge: Judge = live_judge,
                    is_quality: bool = is_quality,
                ) -> ProbeOutcome:
                    async with sem:
                        if is_quality:
                            return await _score_quality_test(
                                t, check, system_prompt, hardened, judge,
                                target_client=target_client, target_model_id=target_model_id,
                            )
                        return await _score_template(
                            t, check, system_prompt, hardened, judge,
                            demonstration=False, target_client=target_client,
                            target_model_id=target_model_id,
                        )

                tasks = [asyncio.create_task(one(t)) for t in templates]
                try:
                    for fut in asyncio.as_completed(tasks):
                        outcome = await fut
                        check_outcomes[outcome.probe_id] = outcome
                        completed += 1
                        yield _probe_event(check, outcome, completed, total, demonstration)
                        if breaker.record(outcome.scored):
                            scored = sum(1 for o in [*outcomes, *check_outcomes.values()] if o.scored)
                            raise ScanAbort(
                                "backend_unavailable",
                                f"{scored} of {completed} attacks scored before the model backend "
                                f"stopped responding reliably ({outcome.error or 'repeated errors'}).",
                            )
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

            ordered = [
                check_outcomes[_unit_id(t)] for t in templates if _unit_id(t) in check_outcomes
            ]
            outcomes.extend(ordered)
            card = await _build_card(
                check, ordered, target_name, judge_model, crosswalk_version, demonstration,
                execution, judge_choice, judge_backend, sampling_pinned, accuracy_for,
                kind=kinds[check],
            )
            cards.append(card)
            yield ScanEvent(
                type=ScanEventType.CHECK_COMPLETED,
                check=check,
                card=card,
                demonstration=demonstration,
                message=f"Grade {card.grade} on {check.replace('_', ' ')}",
            )
    except ScanAbort as abort:
        yield ScanEvent(type=ScanEventType.ERROR, code=abort.code, message=abort.message,
                        completed=completed, total=total, demonstration=demonstration)
        return
    except Exception as exc:  # noqa: BLE001  every stream must end with one terminal event
        abort = _abort_for(exc)
        log.warning("scan aborted (%s): %r", abort.code, exc)
        yield ScanEvent(type=ScanEventType.ERROR, code=abort.code, message=abort.message,
                        completed=completed, total=total, demonstration=demonstration)
        return

    n_scored = sum(1 for o in outcomes if o.scored)
    result = ScanResult(
        target_name=target_name,
        checks=list(checks),
        tier=tier,
        demonstration=demonstration,
        overall_grade=_worst_grade([c.grade for c in cards]),
        cards=cards,
        outcomes=outcomes,
        execution=execution,
        n_planned=total,
        n_scored=n_scored,
        n_errored=len(outcomes) - n_scored,
        hardened_prompt_sha256=hardened_sha,
        target_model=target_model_id or "",
    )
    yield ScanEvent(
        type=ScanEventType.SCAN_COMPLETED,
        result=result,
        demonstration=demonstration,
        message=f"Overall grade {result.overall_grade}",
    )


def _unit_id(unit) -> str:
    return unit["id"] if isinstance(unit, dict) else unit.id


def _probe_event(check: str, outcome: ProbeOutcome, completed: int, total: int, demo: bool) -> ScanEvent:
    return ScanEvent(
        type=ScanEventType.PROBE_RESULT, check=check, probe=outcome,
        completed=completed, total=total, demonstration=demo,
    )


async def _build_card(
    check, outcomes, target_name, judge_model, crosswalk_version, demonstration,
    execution, judge_choice, judge_backend, sampling_pinned, accuracy_for, kind="safety",
):
    scored = [o for o in outcomes if o.scored]
    ba = before_after([bool(o.baseline_issue) for o in scored], [bool(o.hardened_issue) for o in scored])
    bar_a, gold_version, note, source = await accuracy_for(check, judge_model)
    error_kinds: dict[str, int] = {}
    for o in outcomes:
        if not o.scored:
            key = o.error_kind or "unknown"
            error_kinds[key] = error_kinds.get(key, 0) + 1
    trust = TrustInfo(
        execution=execution,
        judge_id=judge_model,
        judge_backend=judge_backend or ("heuristic" if demonstration else "unknown"),
        independence=(
            "n/a (demonstration)" if demonstration
            else getattr(judge_choice, "independence", "") or "undisclosed"
        ),
        independence_disclosure=getattr(judge_choice, "disclosure", "") if judge_choice else "",
        judge_accuracy_source=source if bar_a is not None else "",
        n_planned=len(outcomes),
        n_scored=len(scored),
        n_errored=len(outcomes) - len(scored),
        error_kinds=error_kinds,
        sampling_pinned=sampling_pinned,
    )
    return build_report_card(
        target_name=target_name,
        check=check,
        judge_accuracy=bar_a,
        before_after=ba,
        judge_model=judge_model,
        gold_version=gold_version,
        crosswalk_version=crosswalk_version,
        demonstration=demonstration,
        judge_accuracy_note=note,
        trust=trust,
        kind=kind,
    )


async def _demo_accuracy(check: str, judge_id: str) -> tuple[AccuracyResult | None, str, str, str]:
    acc, gold_version, note = await _demo_calibration(check, "v1")
    return acc, gold_version, note, "committed calibration set (offline stand-in judge)"


async def _live_accuracy_unmeasured(
    check: str, judge_id: str
) -> tuple[AccuracyResult | None, str, str, str]:
    note = (
        f"Not yet measured for judge {judge_id} on this backend: run "
        f"`fusion measure --stages accuracy` to measure it against the labelled gold set."
    )
    return None, "", note, ""


async def _demo_calibration(
    check: str, version: str
) -> tuple[AccuracyResult | None, str, str]:
    """The judge's accuracy on the committed calibration set, its gold version, and a note. A missing or
    stale cassette is reported in the note, never silently dropped."""
    path = CASSETTE_DIR / f"{check}.{version}.json"
    if not path.exists():
        note = f"Judge accuracy unavailable: calibration cassette missing for {check}."
        log.warning(note)
        return None, "", note
    try:
        client = ReplayModelClient(Cassette.load(path), strict=True)
        outcome = await run_calibration(check, client, version=version, split="blind")
    except CassetteMiss:
        note = (
            f"Judge accuracy unavailable: calibration cassette for {check} is stale "
            f"(re-run `fusion record --check {check}`)."
        )
        log.warning(note)
        return None, "", note
    return outcome.result, outcome.gold_version, ""
