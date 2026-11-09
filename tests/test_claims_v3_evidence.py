"""The registered judge-accuracy result under the version-3 wording (PREREG_q7_claims_v3.md) re-derives with no
model: the blind items and their oracle labels from the committed gold v3 and gold v2, the verdicts from the committed
run's `judge.cassette.json` by the recomputed version-3 request keys, then every grader number, subset, baseline and
the decision, equal to the committed envelope. Nothing under `evals/` is written: the scorer runs on a copy of the run
and writes into tmp_path."""

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
from fusion_first.validate.prereg import claims_v3_decision

ROOT = pathlib.Path(__file__).resolve().parents[1]
S = jt.CLAIMS_V3
RUN = ROOT / S.run
PROVENANCE = {"git_sha", "measured"}


@pytest.fixture(scope="module")
def envelope() -> dict:
    return json.loads((ROOT / S.evidence).read_text(encoding="utf-8"))


@pytest.mark.unit
def test_the_envelope_is_the_registered_one_pass(envelope):
    prereg = (ROOT / S.prereg).read_text(encoding="utf-8")
    quoted = re.search(r"Seal digest: `([0-9a-f]{64})`", prereg).group(1)
    assert envelope["seal_digest"] == quoted
    assert envelope["seal_digest"] == jt.seal_status(ROOT / "datasets/gold", ROOT / S.seal, S)["digest"]
    v2 = jt.seal_status(ROOT / "datasets/gold", ROOT / jt.SEAL, jt.TOOLLOOP)["digest"]
    assert envelope["also_graded"]["toolloop"] == {"gold_version": "v2", "seal_digest": v2, "n_items": 80}
    assert v2 in prereg
    assert envelope["scored_once"] is True and envelope["demonstration"] is False
    assert envelope["preregistration"] == S.prereg and envelope["split"] == "blind"
    assert envelope["judge_prompt_version"] == 3 and envelope["study"] == "claims_v3"


@pytest.mark.unit
def test_every_grader_number_re_derives_from_the_gold_and_the_cassette(envelope):
    items = jt.study_items(S, root=ROOT)
    uid_key = json.loads((RUN / "items.json").read_text(encoding="utf-8"))
    cassette = Cassette.load(RUN / "judge.cassette.json").entries
    assert set(uid_key) == {i.uid for i in items} and len(items) == 170
    for check in S.checks:
        its = [i for i in items if i.check == check]
        verdicts = {}
        with judge_prompt_version(3):
            for it in its:
                key = Judge(None)._build_request(it.trajectory, get_rubric(check)).cache_key()
                assert uid_key[it.uid] == key  # the run asked exactly the sealed case's question, at version 3
                entry = cassette[key]
                verdicts[it.uid] = Judge._parse(str(entry["text"]), get_rubric(check), str(entry["model"])).is_issue
        block = envelope["checks"][check]
        y, pred = [i.label for i in its], [verdicts[i.uid] for i in its]
        assert block["grader"] == _block(y, pred, 0, "oracle")
        for src, name in (("claims_v3", "gold_v3"), ("toolloop", "gold_v2")):
            sub = [i for i in its if i.source == src]
            assert block["subsets"][name] == _block([i.label for i in sub], [verdicts[i.uid] for i in sub], 0, "oracle")
        assert block["n_items"] == len(its) and block["positives"] == sum(y)
    assert claims_v3_decision(envelope) == envelope["decision"]


@pytest.mark.unit
def test_the_scorer_re_derives_the_whole_envelope_without_writing_evals(envelope, tmp_path):
    shutil.copytree(RUN, tmp_path / RUNS_DIRNAME / envelope["run_id"])
    out = tmp_path / "rescored.json"
    folder = ROOT / S.dir
    before = sorted(p.stat().st_mtime_ns for p in folder.rglob("*") if p.is_file())
    rescored = jt.score(RunDir(tmp_path, envelope["run_id"]), out=out, root=ROOT, study=S)
    after = sorted(p.stat().st_mtime_ns for p in folder.rglob("*") if p.is_file())
    assert before == after
    assert set(rescored) == set(envelope)
    assert {k: v for k, v in rescored.items() if k not in PROVENANCE} == \
        {k: v for k, v in envelope.items() if k not in PROVENANCE}
