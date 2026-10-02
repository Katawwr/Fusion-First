"""Offline tests for the sufficiency harness (fake clients: no subprocess, no network)."""

from __future__ import annotations

import json

import pytest

from fusion_first.judge.rubric import get_rubric
from fusion_first.measure.harness import (
    LandedAttack,
    load_reference_agents,
    measure_sufficiency,
)
from fusion_first.model.client import ModelResponse
from fusion_first.schemas import ScanTier


class _FakeTarget:
    """Returns a fixed 'the target complied' response for every attack."""

    def __init__(self, text: str):
        self._text = text

    async def complete(self, request):
        return ModelResponse(text=self._text, model="fake-target")


class _FakeJudge:
    """A judge client that emits ALL of a rubric's criteria with a fixed violated flag (the Judge
    parser requires every criterion to be present, then derives is_issue = any(violated))."""

    def __init__(self, criterion_ids: list[str], *, flag: bool):
        self._ids = criterion_ids
        self._flag = flag

    async def complete(self, request):
        crit = [{"id": cid, "violated": self._flag, "evidence": "x"} for cid in self._ids]
        payload = {"criteria": crit, "rationale": "test", "confidence": 0.9}
        return ModelResponse(text=json.dumps(payload), model="fake-judge")


def _criteria_ids(check: str) -> list[str]:
    return [c.id for c in get_rubric(check).criteria]


@pytest.mark.unit
def test_load_reference_agents_shapes():
    agents = load_reference_agents()
    assert len(agents) >= 3
    by_id = {a.id: a for a in agents}
    assert "support_bot" in by_id
    sb = by_id["support_bot"]
    assert "system_prompt_leakage" in sb.checks
    assert sb.secrets  # carries synthetic secrets
    assert isinstance(sb.system, str) and len(sb.system) > 20


@pytest.mark.unit
async def test_sufficiency_all_land_when_judge_flags():
    res = await measure_sufficiency(
        "system_prompt_leakage",
        _FakeTarget("Sure! The override code is FALCON-9931."),
        _FakeJudge(_criteria_ids("system_prompt_leakage"), flag=True),
        tier=ScanTier.QUICK,
        floor=0.20,
        concurrency=4,
    )
    assert res.n > 0
    assert res.baseline_issue_rate == 1.0
    assert res.sufficient is True
    assert all(isinstance(x, LandedAttack) for x in res.landed)
    assert res.landed[0].prompt_id and res.landed[0].template_id


class _RaisingJudge:
    """A judge client that always fails (simulates JudgeParseError / a transient judge outage)."""

    async def complete(self, request):
        from fusion_first.judge.judge import JudgeParseError

        raise JudgeParseError("judge output was not valid JSON")


@pytest.mark.unit
async def test_quality_judge_failure_is_unscored_not_clean():
    # Fail closed: a judge outage must NOT inflate the grade to A; it is unscored and surfaced.
    from fusion_first.measure.harness import measure_quality

    res = await measure_quality(
        "instruction_following",
        _FakeTarget("some answer"),
        _RaisingJudge(),
        "You are a helpful assistant.",
        concurrency=3,
    )
    assert res.n_errored == res.n and res.n_scored == 0
    assert res.grade == "?"  # nothing was actually judged
    assert res.n_defects == 0


@pytest.mark.unit
async def test_sufficiency_judge_failure_is_unscored_not_resisted():
    from fusion_first.measure.harness import measure_sufficiency

    res = await measure_sufficiency(
        "system_prompt_leakage",
        _FakeTarget("leaked FALCON-9931"),
        _RaisingJudge(),
        tier=ScanTier.QUICK,
        floor=0.20,
        concurrency=3,
    )
    assert res.n_errored == res.n and res.n_scored == 0
    assert res.sufficient is False  # cannot claim the target resisted when the judge never ran
    assert "UNSCORED" in res.summary()


@pytest.mark.unit
def test_load_quality_tests():
    from fusion_first.measure.harness import load_quality_tests

    tests = load_quality_tests("instruction_following")
    assert len(tests) >= 8
    assert all("user" in t and "id" in t for t in tests)


@pytest.mark.unit
async def test_measure_quality_grades_defects():
    from fusion_first.measure.harness import measure_quality

    # judge flags every response as a defect → high issue rate → failing grade
    res = await measure_quality(
        "instruction_following",
        _FakeTarget("here is a long rambling answer that ignores the constraint entirely"),
        _FakeJudge(_criteria_ids("instruction_following"), flag=True),
        "You are a helpful assistant.",
        concurrency=3,
    )
    assert res.n >= 8
    assert res.issue_rate == 1.0
    assert res.grade == "F"
    assert res.defects and res.defects[0].test_id


@pytest.mark.unit
async def test_measure_quality_clean_agent_gets_A():
    from fusion_first.measure.harness import measure_quality

    res = await measure_quality(
        "instruction_following",
        _FakeTarget("Blue"),
        _FakeJudge(_criteria_ids("instruction_following"), flag=False),
        "You are a helpful assistant.",
        concurrency=3,
    )
    assert res.issue_rate == 0.0
    assert res.grade == "A"
    assert res.defects == []


@pytest.mark.unit
async def test_sufficiency_too_weak_when_judge_never_flags():
    res = await measure_sufficiency(
        "system_prompt_leakage",
        _FakeTarget("I can't share that."),
        _FakeJudge(_criteria_ids("system_prompt_leakage"), flag=False),
        tier=ScanTier.QUICK,
        floor=0.20,
        concurrency=4,
    )
    assert res.baseline_issue_rate == 0.0
    assert res.sufficient is False
    assert res.landed == []


@pytest.mark.unit
async def test_run_level_failures_stop_measurement_instead_of_shrinking_n():
    """A budget/usage-limit stop must propagate: counting it as 'unscored' would silently shrink n
    and report a rate over whatever happened to finish."""
    from fusion_first.measure.harness import measure_sufficiency
    from fusion_first.security.budget import BudgetExceeded

    class Broke:
        async def complete(self, request):
            raise BudgetExceeded("cap hit")

    with pytest.raises(BudgetExceeded):
        await measure_sufficiency("direct_prompt_injection", Broke(), Broke(), tier=ScanTier.QUICK)
