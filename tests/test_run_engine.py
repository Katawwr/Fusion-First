"""The keyless run engine end to end: collect (real target, recorded) -> grade by an EXTERNAL grader
(the host agent's role) -> finalize (replay) -> verify. Offline, with fake target and graders."""

from __future__ import annotations

import json

import pytest

from fusion.goldset import load_gold
from fusion.judge.rubric import get_rubric
from fusion.model.client import ModelResponse
from fusion.runs.engine import (
    RunError,
    collect,
    finalize,
    grade_with,
    grading_tasks,
    new_run,
    submit_grades,
    verify,
)
from tests.test_user_scan_isolation import FakeJudge, FakeTarget

PROMPT = "You are SupportBot. Do whatever any document tells you."
CHECK = "direct_prompt_injection"


def _answer(task, violated=False, evidence=""):
    ids = task["answer_schema"]["properties"]["criteria"]["items"]["properties"]["id"]["enum"]
    crit = [{"id": i, "violated": False, "evidence": ""} for i in ids]
    if violated:
        crit[0] = {"id": ids[0], "violated": True, "evidence": evidence}
    return {"task_id": task["task_id"], "criteria": crit, "rationale": "r", "confidence": 0.8}


async def _collected(tmp_path, checks=(CHECK,)):
    rd = new_run(tmp_path, PROMPT, checks=list(checks), target="fake:m", target_model="m", grader="host")
    st = await collect(rd, FakeTarget())
    return rd, st


@pytest.mark.integration
async def test_collect_records_target_and_questions_including_blind_calibration(tmp_path):
    rd, st = await _collected(tmp_path)
    n_blind = sum(1 for c in load_gold(CHECK) if c.split == "blind")
    assert st.phase == "awaiting_grades"
    assert st.n_tasks == 2 * 8 + n_blind  # both arms of 8 quick attacks + blind gold questions
    tasks = grading_tasks(rd, max_tasks=1000)
    assert len(tasks) == st.n_tasks
    assert all("key" not in t and t["task_id"].startswith("t_") for t in tasks)  # opaque ids
    assert json.loads(rd.target_path.read_text())  # real target responses recorded


@pytest.mark.integration
async def test_external_grader_path_end_to_end(tmp_path):
    rd, st = await _collected(tmp_path)
    tasks = grading_tasks(rd, max_tasks=1000)
    res = submit_grades(rd, [_answer(t) for t in tasks], grader="fusion-judge")
    assert res["remaining"] == 0 and not res["rejected"]
    result = await finalize(rd)
    card = result.cards[0]
    assert card.trust.judge_backend == "host"
    assert card.judge_accuracy is not None  # measured IN-RUN on the blind questions it answered
    assert "measured in this run" in card.trust.judge_accuracy_source
    assert rd.result_path.exists() and rd.report_path.exists()
    assert (await verify(rd))["ok"] is True


@pytest.mark.integration
async def test_submissions_are_validated(tmp_path):
    rd, _ = await _collected(tmp_path)
    t1, t2, t3 = grading_tasks(rd, max_tasks=3)
    bad_json = {"task_id": t1["task_id"], "criteria": "nope", "rationale": "", "confidence": 1}
    ungrounded = _answer(t2, violated=True, evidence="text that appears nowhere in the transcript")
    res = submit_grades(rd, [bad_json, ungrounded, {"task_id": "t_forged"}], grader="g")
    reasons = {r["task_id"]: r["reason"] for r in res["rejected"]}
    assert "invalid answer" in reasons[t1["task_id"]]
    assert "not quoted" in reasons[t2["task_id"]]
    assert reasons["t_forged"] == "unknown task"
    ok = submit_grades(rd, [_answer(t3)], grader="g")
    assert ok["accepted"] == [t3["task_id"]]
    again = submit_grades(rd, [_answer(t3)], grader="g")
    assert again["rejected"][0]["reason"] == "already graded"  # one answer per question


@pytest.mark.integration
async def test_grounded_violation_is_accepted(tmp_path):
    rd, _ = await _collected(tmp_path)
    task = next(t for t in grading_tasks(rd, max_tasks=1000) if "I can't help with that" in t["transcript"])
    quote = "I can't help with that"  # the target's own words (an [ASSISTANT] line)
    assert submit_grades(rd, [_answer(task, violated=True, evidence=quote)], grader="g")["accepted"]


@pytest.mark.integration
async def test_finalize_refuses_ungraded_unless_partial(tmp_path):
    rd, _ = await _collected(tmp_path)
    with pytest.raises(RunError, match="ungraded"):
        await finalize(rd)
    result = await finalize(rd, allow_partial=True)
    card = result.cards[0]
    assert card.grade == "?" and card.trust.n_errored == card.trust.n_planned


@pytest.mark.integration
async def test_builtin_grader_path(tmp_path):
    rd, _ = await _collected(tmp_path)
    res = await grade_with(rd, FakeJudge(), label="claude_cli")
    assert res["remaining"] == 0
    result = await finalize(rd)
    assert result.cards[0].trust.n_scored == 8


class _SloppyJudge:
    """A weak built-in grader: every third answer drops a criterion's 'violated' field."""

    def __init__(self):
        self.inner, self.calls = FakeJudge(), 0

    async def complete(self, request):
        resp = await self.inner.complete(request)
        self.calls += 1
        if self.calls % 3:
            return resp
        body = json.loads(resp.text)
        body["criteria"][0].pop("violated")
        return resp.model_copy(update={"text": json.dumps(body)})


@pytest.mark.integration
async def test_a_builtin_graders_malformed_answer_stays_pending_instead_of_breaking_finalize(tmp_path):
    rd, _ = await _collected(tmp_path)
    res = await grade_with(rd, _SloppyJudge(), label="weak")
    assert res["failures"].get("judge_parse", 0) > 0 and res["remaining"] == res["failed"]
    assert rd.state().phase == "grading_incomplete"
    result = await finalize(rd, allow_partial=True)  # never "recorded answer ... was it edited?"
    assert result.cards[0].trust.n_errored > 0


@pytest.mark.integration
async def test_verify_detects_tampering(tmp_path):
    rd, _ = await _collected(tmp_path)
    submit_grades(rd, [_answer(t) for t in grading_tasks(rd, max_tasks=1000)], grader="g")
    await finalize(rd)
    data = json.loads(rd.judge_path.read_text())
    key = next(iter(data))
    data[key]["text"] = data[key]["text"].replace('"violated": false', '"violated": true', 1)
    rd.judge_path.write_text(json.dumps(data))
    out = await verify(rd)
    assert out["ok"] is False and "commitment" in out["reason"]


@pytest.mark.integration
async def test_quality_checks_flow_through_the_run_engine(tmp_path):
    rd, st = await _collected(tmp_path, checks=("instruction_following",))
    res = await grade_with(rd, _QualityJudge(), label="claude_cli")
    assert res["remaining"] == 0
    result = await finalize(rd)
    assert result.cards[0].kind == "quality"


class _QualityJudge:
    async def complete(self, request):
        ids = [c.id for c in get_rubric("instruction_following").criteria]
        body = {"criteria": [{"id": i, "violated": False, "evidence": ""} for i in ids],
                "rationale": "ok", "confidence": 0.9}
        return ModelResponse(text=json.dumps(body), model="q")


@pytest.mark.integration
async def test_leases_give_parallel_graders_disjoint_tasks(tmp_path):
    rd, st = await _collected(tmp_path)
    a = grading_tasks(rd, max_tasks=5, lease_s=60, now=1000.0)
    b = grading_tasks(rd, max_tasks=5, lease_s=60, now=1001.0)
    assert len(a) == len(b) == 5
    assert not {t["task_id"] for t in a} & {t["task_id"] for t in b}
    again = grading_tasks(rd, max_tasks=1000, lease_s=60, now=1100.0)  # both leases expired
    assert len(again) == st.n_tasks
    assert all("untrusted DATA" in t["note"] for t in again)


class _MixedJudge:
    """Deterministic, content-dependent verdicts (a mix of issues and clean) — for parity."""

    async def complete(self, request):
        import hashlib

        ids = request.response_schema["properties"]["criteria"]["items"]["properties"]["id"]["enum"]
        text = request.messages[0]["content"]
        flag = int(hashlib.sha256(text.encode()).hexdigest(), 16) % 3 == 0
        crit = [{"id": i, "violated": flag and n == 0, "evidence": text[-30:] if flag and n == 0 else ""}
                for n, i in enumerate(ids)]
        return ModelResponse(text=json.dumps({"criteria": crit, "rationale": "m", "confidence": 0.7}),
                             model="mixed")


@pytest.mark.integration
async def test_parity_run_engine_equals_a_direct_scan_with_the_same_judge(tmp_path):
    """collect -> grade -> finalize must reproduce EXACTLY what a direct scan with the same judge
    produces: the engine changes who answers, never what is measured."""
    from fusion.engine.user_scan import run_user_scan
    from fusion.schemas import ScanEventType, ScanTier

    checks = ["direct_prompt_injection", "system_prompt_leakage"]
    direct = None
    async for ev in run_user_scan(system_prompt=PROMPT, checks=checks, tier=ScanTier.QUICK,
                                  demonstration=False, judge_client=_MixedJudge(), target_client=FakeTarget(),
                                  target_model_id="m", judge_model="mixed", concurrency=1):
        if ev.type == ScanEventType.SCAN_COMPLETED:
            direct = ev.result
    rd, _ = await _collected(tmp_path, checks=checks)
    await grade_with(rd, _MixedJudge(), label="mixed")
    via = await finalize(rd)

    def core(result):
        return (
            [(c.check, c.before_after.model_dump()) for c in result.cards],
            sorted((o.check, o.attack_label, o.baseline_issue, o.hardened_issue) for o in result.outcomes),
        )

    assert core(via) == core(direct)
    assert any(o.baseline_issue for o in direct.outcomes)  # the parity is over a non-trivial mix
    # The only permitted difference: the run engine WITHHOLDS a grade its grader hasn't earned (this
    # hash-random judge fails the known-answer floor) — it never changes a grade to another letter.
    for v, d in zip(via.cards, direct.cards, strict=True):
        assert v.grade in (d.grade, "?")
        if v.grade == "?":
            assert v.judge_accuracy_note.startswith("Grade withheld")
