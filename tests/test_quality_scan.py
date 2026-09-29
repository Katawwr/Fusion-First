"""Quality is a first-class dimension of a scan: graded on both arms, so the card shows the quality
of the prompt as written AND whether the safety fix (the prompt the user ships) hurt it."""

from __future__ import annotations

import json

import pytest

from fusion_first.engine.user_scan import run_user_scan
from fusion_first.model.client import ModelResponse, ModelRole
from fusion_first.schemas import ScanEventType

PROMPT = "You are a concise assistant."

# Good answers for the verifier-graded tests; the hardened arm will be made verbose to cost quality.
GOOD = {
    "primary color": "Red",
    "JSON array": '["Mars", "Venus", "Earth"]',
    "under 12 words": "Gravity pulls masses together.",
    "two sentences": "The ocean is vast. It covers most of Earth.",
    "good morning": "Buenos días",
    "only a number": "7",
    "three bullet points": "* Evaporation\n* Condensation\n* Precipitation",
}


class Target:
    def __init__(self, hurt_when_hardened: bool):
        self.hurt = hurt_when_hardened

    async def complete(self, request):
        assert request.role == ModelRole.TARGET
        user = request.messages[0]["content"]
        answer = next((v for k, v in GOOD.items() if k in user), "A fine, on-task answer.")
        if self.hurt and "Fusion First safety guardrails" in request.system:
            answer = "As a safe assistant I must add context first. " + answer + " Let me elaborate further."
        return ModelResponse(text=answer, model="fake-target")


class Judge:
    def __init__(self):
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        ids = request.response_schema["properties"]["criteria"]["items"]["properties"]["id"]["enum"]
        body = {"criteria": [{"id": i, "violated": False, "evidence": ""} for i in ids],
                "rationale": "ok", "confidence": 0.9}
        return ModelResponse(text=json.dumps(body), model="fake-judge")


async def _scan(target, judge):
    return [ev async for ev in run_user_scan(
        system_prompt=PROMPT, checks=["instruction_following"], demonstration=False,
        judge_client=judge, target_client=target, target_model_id="m", judge_model="fake-judge",
    )]


@pytest.mark.unit
async def test_quality_scan_uses_verifiers_where_possible_and_the_judge_otherwise():
    judge = Judge()
    events = await _scan(Target(hurt_when_hardened=False), judge)
    done = events[-1]
    assert done.type == ScanEventType.SCAN_COMPLETED
    card = done.result.cards[0]
    assert card.kind == "quality"
    assert card.trust.n_planned == 10 and card.trust.n_scored == 10
    assert judge.calls == 2 * 3  # only the 3 tests without a verifier spec are judged (both arms)
    assert card.grade == "A"
    assert any("Quality held" in f for f in card.top_fixes)


@pytest.mark.unit
async def test_quality_fix_cost_is_flagged_when_the_hardened_prompt_hurts():
    events = await _scan(Target(hurt_when_hardened=True), Judge())
    card = events[-1].result.cards[0]
    ba = card.before_after
    assert ba.hardened_issue_rate > ba.baseline_issue_rate
    assert any("made quality worse" in f for f in card.top_fixes)


@pytest.mark.unit
async def test_quality_needs_a_live_model():
    with pytest.raises(ValueError, match="live model"):
        async for _ in run_user_scan(system_prompt=PROMPT, checks=["instruction_following"], demonstration=True):
            pass


@pytest.mark.unit
async def test_safety_and_quality_in_one_scan():
    from tests.test_user_scan_isolation import FakeJudge, FakeTarget

    events = [ev async for ev in run_user_scan(
        system_prompt=PROMPT, checks=["direct_prompt_injection", "instruction_following"],
        demonstration=False, judge_client=FakeJudge(), target_client=FakeTarget(),
        target_model_id="m", judge_model="fake-judge",
    )]
    done = events[-1]
    assert done.type == ScanEventType.SCAN_COMPLETED
    assert [c.kind for c in done.result.cards] == ["safety", "quality"]
