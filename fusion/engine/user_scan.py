"""User-prompt scan: the web-app pipeline that turns a pasted system prompt into a Safety Report.

For each requested check we run every attack template against two arms of the user's prompt —
baseline (as pasted) and hardened (`apply_fix` applied) — judge both, and fold the results into
the existing paired statistics and report card. The whole thing is emitted as a stream of
`ScanEvent`s so the HTTP layer can show live progress without the engine knowing about HTTP.

Two modes, one pipeline:
  - DEMO (keyless, deterministic): the arms use the templates' canned responses and the judge is
    the offline heuristic, replayed through the real Judge code path via a trajectory cassette.
    Every card is stamped `demonstration=True`.
  - LIVE (real keys): the user's prompt is run through a real target model to produce each arm's
    response, and a real judge scores them. Cards are real (`demonstration=False`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fusion.attacks.taxonomy import Crosswalk
from fusion.attacks.templates import AttackTemplate, select_templates
from fusion.engine.fixes import apply_fix
from fusion.engine.report import build_report_card
from fusion.judge.judge import Judge
from fusion.judge.rubric import get_rubric
from fusion.model.client import ModelClient, ModelRequest, ModelRole
from fusion.model.replay import Cassette, ReplayModelClient
from fusion.recording import CASSETTE_DIR, build_trajectory_cassette
from fusion.schemas import (
    AccuracyResult,
    ProbeOutcome,
    ScanEvent,
    ScanEventType,
    ScanResult,
    ScanTier,
    Trajectory,
    Verdict,
)
from fusion.stats.calibration import run_calibration
from fusion.stats.paired import before_after

DEMO_JUDGE_MODEL = "demo-heuristic-judge"
_GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "?": 5}


def _worst_grade(grades: list[str]) -> str:
    return max(grades, key=lambda g: _GRADE_RANK.get(g, 5)) if grades else "?"


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
    """A judge that replays offline heuristic verdicts through the production Judge code path."""
    cassette = build_trajectory_cassette(trajectories, check)
    return Judge(ReplayModelClient(cassette, strict=True))


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
) -> AsyncIterator[ScanEvent]:
    """Stream a full user-prompt scan as ScanEvents. See module docstring for the two modes."""
    if not demonstration and judge_client is None:
        raise ValueError("live scan requires a judge_client")
    judge_model = judge_model or (DEMO_JUDGE_MODEL if demonstration else "judge")
    crosswalk_version = Crosswalk().code_version()

    plan = {check: select_templates(check, tier, version) for check in checks}
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
    for check in checks:
        templates = plan[check]
        rubric = get_rubric(check)
        hardened_prompt = apply_fix(system_prompt, [check])
        yield ScanEvent(
            type=ScanEventType.CHECK_STARTED,
            check=check,
            total=len(templates),
            demonstration=demonstration,
            message=f"Attacking your prompt: {check.replace('_', ' ')}",
        )

        # Build both arms for every template first (needed to seed the demo judge cassette).
        arms: list[tuple[AttackTemplate, Trajectory, Trajectory]] = []
        for template in templates:
            base_traj, hard_traj = await _build_arms(
                template,
                system_prompt,
                hardened_prompt,
                demonstration=demonstration,
                target_client=target_client,
                target_model_id=target_model_id,
            )
            arms.append((template, base_traj, hard_traj))

        if demonstration:
            all_trajs = [t for _, b, h in arms for t in (b, h)]
            judge = _demo_judge(all_trajs, check)
        else:
            judge = Judge(judge_client)

        baseline_fail: list[bool] = []
        hardened_fail: list[bool] = []
        for template, base_traj, hard_traj in arms:
            b: Verdict = await judge.evaluate(base_traj, rubric)
            h: Verdict = await judge.evaluate(hard_traj, rubric)
            baseline_fail.append(b.is_issue)
            hardened_fail.append(h.is_issue)
            outcome = ProbeOutcome(
                check=check,
                probe_id=template.id,
                attack_label=template.attack_label,
                owasp=template.owasp,
                baseline_issue=b.is_issue,
                hardened_issue=h.is_issue,
                baseline_severity=b.severity,
                hardened_severity=h.severity,
            )
            outcomes.append(outcome)
            completed += 1
            yield ScanEvent(
                type=ScanEventType.PROBE_RESULT,
                check=check,
                probe=outcome,
                completed=completed,
                total=total,
                demonstration=demonstration,
            )

        ba = before_after(baseline_fail, hardened_fail)
        bar_a, gold_version = await _demo_calibration(check, version) if demonstration else (None, "")
        card = build_report_card(
            target_name=target_name,
            check=check,
            judge_accuracy=bar_a,
            before_after=ba,
            judge_model=judge_model,
            gold_version=gold_version,
            crosswalk_version=crosswalk_version,
            demonstration=demonstration,
        )
        cards.append(card)
        yield ScanEvent(
            type=ScanEventType.CHECK_COMPLETED,
            check=check,
            card=card,
            demonstration=demonstration,
            message=f"Grade {card.grade} on {check.replace('_', ' ')}",
        )

    result = ScanResult(
        target_name=target_name,
        checks=list(checks),
        tier=tier,
        demonstration=demonstration,
        overall_grade=_worst_grade([c.grade for c in cards]),
        cards=cards,
        outcomes=outcomes,
    )
    yield ScanEvent(
        type=ScanEventType.SCAN_COMPLETED,
        result=result,
        demonstration=demonstration,
        message=f"Overall grade {result.overall_grade}",
    )


async def _demo_calibration(check: str, version: str) -> tuple[AccuracyResult | None, str]:
    """The judge's accuracy on our committed calibration set (a property of the judge, not the
    user's prompt) plus that gold set's version. Best-effort: on any hiccup the card omits Bar A."""
    path = CASSETTE_DIR / f"{check}.{version}.json"
    if not path.exists():
        return None, ""
    try:
        client = ReplayModelClient(Cassette.load(path), strict=False)
        outcome = await run_calibration(check, client, version=version, split="blind")
        return outcome.result, outcome.gold_version
    except Exception:  # noqa: BLE001 — Bar A is a bonus; never fail a scan over it
        return None, ""
