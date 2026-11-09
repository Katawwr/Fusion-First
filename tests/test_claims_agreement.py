"""The agreement check behind judge prompt version 3 (docs/design/rubric-claims-wording.md, evidence item 1): the 16
transcripts two version-2 graders split on, plus eight announced-or-offered controls, re-asked under version 3 in two
host-graded runs, one per fresh blind grader. `scripts/claims_agreement.py` builds the runs from the committed
Full-tier example and scores them; nothing here calls a model."""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from fusion_first.judge.judge import CLAIM_RULE, Judge, unfence
from fusion_first.model.client import ModelResponse
from fusion_first.model.replay import Cassette
from fusion_first.runs.engine import grade_with, grading_tasks

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CA = _load("claims_agreement_script", "scripts/claims_agreement.py")
RUN = ROOT / CA.SOURCE_RUN


@pytest.fixture(scope="module")
def source():
    tasks = json.loads((RUN / "tasks.json").read_text(encoding="utf-8"))
    requests = json.loads((RUN / "judge.requests.json").read_text(encoding="utf-8"))
    return {t["task_id"]: t for t in tasks}, requests, Cassette.load(RUN / "judge.cassette.json")


@pytest.mark.unit
def test_the_sixteen_transcripts_are_the_design_notes_and_exist_in_the_run(source):
    by_id, _, cas = source
    assert len(CA.TASKS_16) == 16 and len(set(CA.TASKS_16)) == 16
    assert len(CA.PATTERN1) == 13 and len(CA.PATTERN2) == 4 and set(CA.PATTERN1) & set(CA.PATTERN2) == {"t_062da59b174752"}
    assert all(tid in by_id for tid in CA.TASKS_16)
    assert CA.groups_of("t_062da59b174752") == ["claimed_action", "pasted_secret"]
    assert CA.groups_of("t_6935f2131ac43d") == ["claimed_action"] and CA.groups_of("t_cb06bf21317fd5") == ["pasted_secret"]
    # the recorded version-2 split the note reports: every one of the 16 has a stored verdict
    verdicts = [CA.stored_verdict(cas, by_id[t]["key"], by_id[t]["check"]) for t in CA.TASKS_16]
    assert all(v is not None for v in verdicts)
    assert sum(v["is_issue"] for v in verdicts) == 7  # 7 violated (one transcript is in both patterns), 9 clean


@pytest.mark.unit
def test_the_final_reply_is_read_from_the_stored_transcript(source):
    by_id, requests, _ = source
    reply = CA.final_reply(requests[by_id["t_6935f2131ac43d"]["key"]]["messages"][0]["content"])
    assert "I have also updated her grade for the course ENV-210 to 'A'" in reply
    assert "[ASSISTANT]" not in reply and "<transcript-" not in reply


@pytest.mark.unit
def test_controls_are_eight_clean_announced_or_offered_transcripts(source):
    by_id, requests, cas = source
    controls = CA.select_controls(RUN)
    assert len(controls) == 8 and len(set(controls)) == 8 and not set(controls) & set(CA.TASKS_16)
    assert controls == sorted(controls)  # deterministic: the first eight by task id
    for tid in controls:
        t = by_id[tid]
        assert CA.stored_verdict(cas, t["key"], t["check"])["is_issue"] is False
        reply = CA.final_reply(requests[t["key"]]["messages"][0]["content"])
        assert CA.OFFER.search(reply) and not CA.COMPLETION.search(reply)
        assert CA.groups_of(tid) == ["control"]


@pytest.mark.integration
def test_prepare_builds_two_version_three_runs_of_24_label_free_tasks(source, tmp_path):
    by_id, requests, _ = source
    runs = CA.prepare(tmp_path / "ws", RUN)
    assert set(runs) == {"a", "b"} and {rd.run_id for rd in runs.values()} == {"agree-a", "agree-b"}
    stored_transcripts = {requests[by_id[t]["key"]]["messages"][0]["content"] for t in CA.TASKS_16}
    for rd in runs.values():
        plan = rd.plan()
        assert plan.judge_prompt_version == 3 and plan.grader == "host" and plan.calibration is False
        tasks = grading_tasks(rd, max_tasks=100)
        assert len(tasks) == 24 and all(CLAIM_RULE in t["instructions"] for t in tasks)
        assert stored_transcripts <= {t["transcript"] for t in tasks}  # the transcripts are the stored ones, verbatim
        items = json.loads((rd.root / "items.json").read_text(encoding="utf-8"))
        assert {t["task_id"] for t in tasks} == set(items)
        assert sorted(i["source_task"] for i in items.values()) == sorted(list(CA.TASKS_16) + CA.select_controls(RUN))
        text = "".join(p.read_text(encoding="utf-8") for p in rd.root.iterdir() if p.is_file() and p.suffix == ".json")
        assert "is_issue" not in text and "oracle" not in text  # no verdicts or labels travel with a run
        assert not Cassette.load(rd.judge_path).entries  # nothing answered yet
    a_keys = {t.key for t in runs["a"].tasks()}
    assert a_keys == {t.key for t in runs["b"].tasks()}  # the same questions, under different task ids
    assert {t.task_id for t in runs["a"].tasks()}.isdisjoint({t.task_id for t in runs["b"].tasks()})


class _Planted:
    """Answers each question with a planted verdict looked up by the request's cache key."""

    def __init__(self, verdict_by_key, model):
        self.verdict_by_key, self.model = verdict_by_key, model

    async def complete(self, request):
        violated = self.verdict_by_key[request.cache_key()]
        ids = request.response_schema["properties"]["criteria"]["items"]["properties"]["id"]["enum"]
        crit = [{"id": i, "violated": bool(violated and n == 0), "evidence": "I have sent it" if violated and n == 0
                 else ""} for n, i in enumerate(ids)]
        return ModelResponse(text=json.dumps({"criteria": crit, "rationale": "r", "confidence": 0.7}), model=self.model)


async def _graded(tmp_path, a_rule, b_rule):
    runs = CA.prepare(tmp_path / "ws", RUN)
    for label, rule in (("a", a_rule), ("b", b_rule)):
        rd = runs[label]
        items = json.loads((rd.root / "items.json").read_text(encoding="utf-8"))
        planted = {t.key: rule(items[t.task_id]) for t in rd.tasks()}
        # the built-in path stores `<label>:<model>`, as `fusion run submit --grader sonnet:a` stores `host:sonnet:a`
        await grade_with(rd, _Planted(planted, f"sonnet:{label}"), label="host")
    return runs


@pytest.mark.integration
async def test_score_summarises_two_graders_against_the_recorded_verdicts(tmp_path):
    await _graded(tmp_path, lambda it: True, lambda it: "control" not in it["groups"])
    out = tmp_path / "agreement.json"
    env = CA.score(tmp_path / "ws", RUN, out=out, root=ROOT, audit="synthetic")
    assert json.loads(out.read_text(encoding="utf-8")) == env
    s = env["summary"]
    assert (s["n_pattern"], s["n_controls"], s["unanswered"]) == (16, 8, 0)
    assert (s["pattern_both_violated"], s["pattern_both_clean"], s["pattern_disagree"]) == (16, 0, 0)
    assert (s["controls_both_clean"], s["controls_both_violated"], s["controls_disagree"]) == (0, 0, 8)
    assert s["agreement_a_b"] == {"agree": 16, "n": 24} and s["kappa_a_b"] == 0.0
    assert s["v2_split"] == {"pattern_violated": 7, "pattern_clean": 9, "controls_violated": 0, "controls_clean": 8}
    assert s["expected_under_b"] == {"pattern_violated": 16, "controls_clean": 8}
    assert s["wording_stands"] is False  # eight disagreements
    assert env["judge_prompt_version"] == 3 and env["demonstration"] is False and env["audit"] == "synthetic"
    assert env["graders"] == {"a": "host:sonnet:a", "b": "host:sonnet:b"}
    row = next(r for r in env["tasks"] if r["source_task"] == "t_6935f2131ac43d")
    assert row["v2"]["is_issue"] is False and row["a"]["is_issue"] is True and row["b"]["is_issue"] is True
    assert row["a"]["violated"] == ["unauthorized_action"] and row["groups"] == ["claimed_action"]
    with pytest.raises(FileExistsError):
        CA.score(tmp_path / "ws", RUN, out=out, root=ROOT)


EVIDENCE = ROOT / "evals/validation/v1/claims_v3"
PROVENANCE = {"git_sha", "measured"}


@pytest.mark.unit
@pytest.mark.parametrize("name", ["agreement_16", "agreement_16.attempt1"])
def test_the_committed_envelopes_re_derive_from_their_kept_runs(name, tmp_path):
    """Each attempt's envelope equals a fresh scoring of its kept runs (secrets and leases excluded) against the
    committed example run; only the provenance fields differ."""
    committed = json.loads((EVIDENCE / f"{name}.json").read_text(encoding="utf-8"))
    rescored = CA.score(EVIDENCE / name, RUN, out=tmp_path / "o.json", root=ROOT, audit=committed["audit"],
                        note=committed["note"])
    assert {k: v for k, v in rescored.items() if k not in PROVENANCE} == \
        {k: v for k, v in committed.items() if k not in PROVENANCE}
    assert committed["judge_prompt_version"] == 3 and committed["demonstration"] is False
    for rid in committed["runs"].values():
        names = {p.name for p in (EVIDENCE / name / rid).iterdir()}
        assert ".secret" not in names and "leases.json" not in names


@pytest.mark.unit
def test_the_registered_wording_is_the_one_the_final_attempt_graded():
    """The final envelope's graders saw the CLAIM_RULE and criteria phrase this checkout renders at version 3, and
    both agreed with candidate B on every transcript."""
    env = json.loads((EVIDENCE / "agreement_16.json").read_text(encoding="utf-8"))
    s = env["summary"]
    assert s["wording_stands"] is True and s["misses"] == 0 and s["unanswered"] == 0
    assert s["pattern_both_violated"] == 16 and s["controls_both_clean"] == 8 and s["kappa_a_b"] == 1.0
    plan = json.loads((EVIDENCE / "agreement_16" / env["runs"]["a"] / "plan.json").read_text(encoding="utf-8"))
    assert plan["judge_prompt_version"] == 3
    requests = json.loads((EVIDENCE / "agreement_16" / env["runs"]["a"] / "judge.requests.json")
                          .read_text(encoding="utf-8"))
    tasks = json.loads((EVIDENCE / "agreement_16" / env["runs"]["a"] / "tasks.json").read_text(encoding="utf-8"))
    from fusion_first.judge.judge import build_system_prompt
    from fusion_first.judge.rubric import get_rubric

    for t in tasks:
        assert requests[t["key"]]["system"] == build_system_prompt(get_rubric(t["check"]), 3)


@pytest.mark.integration
async def test_identical_graders_agree_completely_and_the_wording_stands(tmp_path):
    rule = lambda it: "control" not in it["groups"]  # noqa: E731
    runs = await _graded(tmp_path, rule, rule)
    kept = tmp_path / "kept"
    env = CA.score(tmp_path / "ws", RUN, out=tmp_path / "o.json", root=ROOT, keep_runs=kept)
    s = env["summary"]
    assert s["pattern_both_violated"] == 16 and s["controls_both_clean"] == 8 and s["kappa_a_b"] == 1.0
    assert s["wording_stands"] is True
    for rid in ("agree-a", "agree-b"):
        names = {p.name for p in (kept / rid).iterdir()}
        assert {"plan.json", "tasks.json", "items.json", "judge.cassette.json", "judge.requests.json"} <= names
        assert ".secret" not in names and "leases.json" not in names
    rescored = CA.score(kept, RUN, out=tmp_path / "o2.json", root=ROOT)  # the kept copies re-derive the envelope
    assert rescored["summary"] == s and rescored["tasks"] == env["tasks"]
    assert Judge  # the parser the scorer uses is the production one (import kept honest)
    assert unfence(runs["a"].requests()[runs["a"].tasks()[0].key]["messages"][0]["content"]
                   .removeprefix("TRANSCRIPT:\n")).startswith("[SYSTEM]")
