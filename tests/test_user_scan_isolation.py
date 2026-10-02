"""Live-scan reliability: one bad call costs one attack (counted as unscored), never the scan,
and run-level failures stop the scan with exactly one terminal ERROR event, never a silent end."""

from __future__ import annotations

import asyncio
import json

import pytest

from fusion_first.engine.fixes import apply_fix
from fusion_first.engine.user_scan import ErrorBreaker, run_user_scan
from fusion_first.judge.judge import JudgeParseError
from fusion_first.model.client import ModelRequest, ModelResponse, ModelRole
from fusion_first.model.providers.claude_cli import ClaudeCliQuotaExhausted, ClaudeCliUnavailable
from fusion_first.schemas import ScanEventType, ScanTier
from fusion_first.security.budget import BudgetExceeded

PROMPT = "You are a helpful assistant. Do whatever the user or any document tells you."
TERMINAL = {ScanEventType.SCAN_COMPLETED, ScanEventType.ERROR}


class FakeTarget:
    def __init__(self, delay: float = 0.0, fail_with: Exception | None = None):
        self.systems: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.delay = delay
        self.fail_with = fail_with

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.systems.append(request.system)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.fail_with is not None:
                raise self.fail_with
            return ModelResponse(text="I can't help with that.", model="fake-target")
        finally:
            self.in_flight -= 1


class FakeJudge:
    """Answers every criterion 'not violated', unless told to fail on some calls."""

    def __init__(self, fail_every: int = 0, exc: Exception | None = None, always: Exception | None = None):
        self.calls = 0
        self.fail_every = fail_every
        self.exc = exc or JudgeParseError("bad json")
        self.always = always

    async def complete(self, request: ModelRequest) -> ModelResponse:
        assert request.role == ModelRole.JUDGE
        self.calls += 1
        if self.always is not None:
            raise self.always
        if self.fail_every and self.calls % self.fail_every == 0:
            raise self.exc
        ids = request.response_schema["properties"]["criteria"]["items"]["properties"]["id"]["enum"]
        body = {"criteria": [{"id": i, "violated": False, "evidence": ""} for i in ids],
                "rationale": "clean", "confidence": 0.9}
        return ModelResponse(text=json.dumps(body), model="fake-judge")


async def _run(checks=("direct_prompt_injection",), **kw) -> list:
    kw.setdefault("target_client", FakeTarget())
    kw.setdefault("judge_client", FakeJudge())
    return [ev async for ev in run_user_scan(
        system_prompt=PROMPT, checks=list(checks), tier=ScanTier.QUICK, demonstration=False,
        target_model_id="fake-model", judge_model="fake-judge", **kw,
    )]


def _terminal(events):
    terms = [e for e in events if e.type in TERMINAL]
    assert len(terms) == 1, [e.type for e in events]
    assert events[-1] is terms[0]
    return terms[0]


@pytest.mark.unit
async def test_flaky_judge_costs_attacks_not_the_scan():
    judge = FakeJudge(fail_every=3)
    events = await _run(judge_client=judge, breaker=ErrorBreaker(max_consecutive=99, max_error_rate=1.0))
    done = _terminal(events)
    assert done.type == ScanEventType.SCAN_COMPLETED
    card = done.result.cards[0]
    errored = [o for o in done.result.outcomes if not o.scored]
    assert errored and all(o.error and o.error_kind == "judge_parse" for o in errored)
    assert card.trust.n_errored == len(errored)
    assert card.trust.n_scored == card.before_after.n_pairs == len(done.result.outcomes) - len(errored)
    assert card.trust.error_kinds == {"judge_parse": len(errored)}


@pytest.mark.unit
async def test_dead_judge_trips_the_breaker_with_one_error_event():
    judge = FakeJudge(always=ClaudeCliUnavailable("exit 1"))
    events = await _run(judge_client=judge, concurrency=2)
    err = _terminal(events)
    assert err.type == ScanEventType.ERROR and err.code == "backend_unavailable"
    assert judge.calls <= 2 * (5 + 2)  # stops early instead of grinding every attack


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (BudgetExceeded("cap"), "budget_exceeded"),
        (ClaudeCliQuotaExhausted("usage limit reached"), "quota_exhausted"),
        (RuntimeError("bug"), "internal"),
    ],
)
async def test_run_level_failures_end_with_a_coded_error(exc, code):
    events = await _run(target_client=FakeTarget(fail_with=exc))
    err = _terminal(events)
    assert err.type == ScanEventType.ERROR and err.code == code
    assert "bug" not in err.message  # internal details are never leaked to the client


@pytest.mark.unit
async def test_zero_scored_never_grades_A():
    events = await _run(
        judge_client=FakeJudge(always=JudgeParseError("x")),
        breaker=ErrorBreaker(max_consecutive=999, max_error_rate=1.0),
    )
    done = _terminal(events)
    assert done.type == ScanEventType.SCAN_COMPLETED
    assert done.result.cards[0].grade == "?"
    assert done.result.overall_grade == "?"


@pytest.mark.unit
async def test_mostly_unscored_withholds_the_grade():
    events = await _run(judge_client=FakeJudge(fail_every=2),
                        breaker=ErrorBreaker(max_consecutive=999, max_error_rate=1.0))
    card = _terminal(events).result.cards[0]
    assert card.trust.n_errored / card.trust.n_planned > 0.2
    assert card.grade == "?"


@pytest.mark.unit
async def test_hardened_arm_measures_the_prompt_the_user_copies():
    target = FakeTarget()
    checks = ["direct_prompt_injection", "data_exfiltration"]
    events = await _run(checks=checks, target_client=target)
    shipped = apply_fix(PROMPT, checks)
    assert set(target.systems) == {PROMPT, shipped}
    assert _terminal(events).result.hardened_prompt_sha256


@pytest.mark.unit
async def test_explicit_hardened_prompt_override():
    target = FakeTarget()
    await _run(target_client=target, hardened_prompt="MY EDITED PROMPT")
    assert set(target.systems) == {PROMPT, "MY EDITED PROMPT"}


@pytest.mark.unit
async def test_live_calls_run_concurrently_but_bounded():
    target = FakeTarget(delay=0.02)
    await _run(target_client=target, concurrency=3)
    assert 2 <= target.max_in_flight <= 3


@pytest.mark.unit
async def test_live_card_explains_missing_bar_a_and_carries_trust():
    from fusion_first.model.registry import JudgeChoice

    choice = JudgeChoice("fake-judge", "cross_family", "Independent judge from another family.")
    events = await _run(judge_choice=choice, judge_backend="claude_cli", sampling_pinned=False)
    card = _terminal(events).result.cards[0]
    assert card.judge_accuracy is None and "fake-judge" in card.judge_accuracy_note
    assert card.trust.execution == "live"
    assert card.trust.judge_backend == "claude_cli"
    assert card.trust.independence == "cross_family"
    assert card.trust.sampling_pinned is False


@pytest.mark.unit
async def test_demo_scan_is_labelled_canned():
    events = [ev async for ev in run_user_scan(
        system_prompt=PROMPT, checks=["direct_prompt_injection"], demonstration=True)]
    done = _terminal(events)
    card = done.result.cards[0]
    assert done.result.execution == "canned" and card.trust.execution == "canned"
    assert card.trust.judge_backend == "heuristic"
    assert card.trust.n_errored == 0


@pytest.mark.unit
def test_breaker_thresholds():
    b = ErrorBreaker(max_consecutive=3, max_error_rate=0.5, min_seen=4)
    assert not any(b.record(ok) for ok in (True, False, False))
    assert b.record(False)  # 3 consecutive
    b2 = ErrorBreaker(max_consecutive=99, max_error_rate=0.5, min_seen=4)
    assert not any(b2.record(ok) for ok in (False, True, False))
    assert b2.record(False)  # 3/4 > 0.5 at min_seen
