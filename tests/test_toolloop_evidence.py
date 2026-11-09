"""The registered tool-trajectory judge-accuracy result (PREREG_q1_toolloop.md) re-derives with no model: the blind
items and their oracle labels from the committed gold, the verdicts from the committed run's `judge.cassette.json` by
the recomputed request keys, then every grader number, baseline and the decision, equal to the committed envelope.
Nothing under `evals/` is written: the scorer runs on a copy of the run and writes into tmp_path."""

from __future__ import annotations

import json
import pathlib
import re
import shutil

import pytest

from fusion_first.judge.judge import Judge, judge_prompt_version
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.replay import Cassette
from fusion_first.runs.engine import RUNS_DIRNAME, RunDir
from fusion_first.validate import judge_eval_toolloop as jt
from fusion_first.validate.judge_eval import _block
from fusion_first.validate.prereg import toolloop_decision

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = ROOT / "evals/validation/v1/toolloop/judge_eval_toolloop_host_sonnet"
# Provenance of the one scoring pass: the commit and the date it ran, not re-derivable from the data.
PROVENANCE = {"git_sha", "measured"}


@pytest.fixture(scope="module")
def envelope() -> dict:
    return json.loads((ROOT / jt.EVIDENCE).read_text(encoding="utf-8"))


@pytest.mark.unit
def test_the_envelope_is_the_registered_one_pass(envelope):
    prereg = (ROOT / jt.PREREG).read_text(encoding="utf-8")
    quoted = re.search(r"Seal digest: `([0-9a-f]{64})`", prereg).group(1)
    assert envelope["seal_digest"] == quoted
    assert envelope["seal_digest"] == jt.seal_status(ROOT / "datasets/gold", ROOT / jt.SEAL)["digest"]
    assert envelope["scored_once"] is True and envelope["demonstration"] is False
    assert envelope["preregistration"] == jt.PREREG and envelope["split"] == "blind"


@pytest.mark.unit
def test_every_grader_number_re_derives_from_the_gold_and_the_cassette(envelope):
    """Independent of the scorer's loop: labels from the oracles, verdicts parsed from the cassette by recomputed keys."""
    items = jt.blind_items(root=ROOT)
    uid_key = json.loads((RUN / "items.json").read_text(encoding="utf-8"))
    cassette = Cassette.load(RUN / "judge.cassette.json").entries
    assert set(uid_key) == {i.uid for i in items}
    for check in jt.CHECKS:
        its = [i for i in items if i.check == check]
        verdicts = {}
        with judge_prompt_version(jt.TOOLLOOP.judge_prompt_version):  # the registered pass ran under version 2
            for it in its:
                key = Judge(None)._build_request(it.trajectory, get_rubric(check)).cache_key()
                assert uid_key[it.uid] == key  # the run asked exactly the sealed case's question
                entry = cassette[key]
                verdicts[it.uid] = Judge._parse(str(entry["text"]), get_rubric(check), str(entry["model"])).is_issue
        y = [i.label for i in its]
        pred = [verdicts[i.uid] for i in its]
        block = envelope["checks"][check]
        assert block["grader"] == _block(y, pred, 0, "oracle")
        assert block["n_items"] == len(its) and block["positives"] == sum(y)
    assert toolloop_decision(envelope) == envelope["decision"]


@pytest.mark.unit
def test_the_scorer_re_derives_the_whole_envelope_without_writing_evals(envelope, tmp_path):
    shutil.copytree(RUN, tmp_path / RUNS_DIRNAME / envelope["run_id"])
    out = tmp_path / "rescored.json"
    before = sorted(p.stat().st_mtime_ns for p in (ROOT / "evals/validation/v1/toolloop").rglob("*") if p.is_file())
    rescored = jt.score(RunDir(tmp_path, envelope["run_id"]), out=out, root=ROOT)
    after = sorted(p.stat().st_mtime_ns for p in (ROOT / "evals/validation/v1/toolloop").rglob("*") if p.is_file())
    assert before == after
    assert set(rescored) == set(envelope)
    assert {k: v for k, v in rescored.items() if k not in PROVENANCE} == \
        {k: v for k, v in envelope.items() if k not in PROVENANCE}
