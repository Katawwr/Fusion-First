"""Live recording and calibration must survive real-world failures without lying.

* One failed judge call costs one case (reported), never the whole recording.
* A run-level stop (usage limit) saves progress; a re-run resumes and only asks for what's missing.
* A stand-in (demo) cassette is never mixed into a real recording.
* Calibration counts unscored gold cases; the gate fails when coverage is too low.
* Replay refuses entries recorded by an unexpected model; `prove` labels cards from provenance.
"""

from __future__ import annotations

import json

import pytest

from fusion_first.goldset import load_gold
from fusion_first.judge.judge import JudgeParseError
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.client import ModelResponse
from fusion_first.model.providers.claude_cli import ClaudeCliQuotaExhausted, ClaudeCliUnavailable
from fusion_first.model.replay import (
    Cassette,
    ProvenanceMismatch,
    ReplayModelClient,
    cassette_provenance,
)
from fusion_first.recording import build_full_cassette, record_gold_cassette_live
from fusion_first.stats.calibration import run_calibration
from fusion_first.stats.gate import evaluate_gate

CHECK = "direct_prompt_injection"
BLIND = [c for c in load_gold(CHECK) if c.split == "blind"]


class Judge:
    """Fake real judge: valid all-clear verdicts; can fail specific call numbers."""

    def __init__(self, fail_calls=(), exc=None, model="claude-sonnet-5"):
        self.calls = 0
        self.fail_calls = set(fail_calls)
        self.exc = exc or ClaudeCliUnavailable("transient")
        self.model = model
        self.ids = [c.id for c in get_rubric(CHECK).criteria]

    async def complete(self, request):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise self.exc
        crit = [{"id": i, "violated": False, "evidence": ""} for i in self.ids]
        return ModelResponse(text=json.dumps({"criteria": crit, "rationale": "r", "confidence": 0.8}), model=self.model)


@pytest.mark.integration
async def test_failed_cases_are_reported_and_resume_only_retries_them(tmp_path):
    path = tmp_path / "c.json"
    first = await record_gold_cassette_live(
        CHECK, Judge(fail_calls={2, 5}), splits=("blind",), include_probes=False,
        concurrency=1, path=path,
    )
    assert len(first.failed) == 2 and first.aborted is None
    assert len(first.cassette) == len(BLIND) - 2
    healthy = Judge()
    second = await record_gold_cassette_live(
        CHECK, healthy, splits=("blind",), include_probes=False, concurrency=1, path=path,
    )
    assert second.ok and healthy.calls == 2  # only the two missing answers were requested
    assert len(Cassette.load(path)) == len(BLIND)


@pytest.mark.integration
async def test_usage_limit_stops_and_keeps_progress(tmp_path):
    path = tmp_path / "c.json"
    report = await record_gold_cassette_live(
        CHECK, Judge(fail_calls={4}, exc=ClaudeCliQuotaExhausted("usage limit reached")),
        splits=("blind",), include_probes=False, concurrency=1, path=path, every=1,
    )
    assert report.aborted and "quota_exhausted" in report.aborted
    assert len(Cassette.load(path)) == 3  # the three answers before the stop are safe on disk


@pytest.mark.integration
async def test_demo_cassette_is_never_resumed_into_a_real_recording(tmp_path):
    path = tmp_path / "c.json"
    build_full_cassette(CHECK).save(path)  # stand-in verdicts
    report = await record_gold_cassette_live(
        CHECK, Judge(), splits=("blind",), include_probes=False, path=path,
    )
    prov = cassette_provenance(Cassette.load(path))
    assert prov.models == {"claude-sonnet-5"} and not prov.demonstration and not prov.mixed
    assert report.recorded == len(BLIND)


@pytest.mark.integration
async def test_calibration_counts_unscored_cases_and_gate_flags_low_coverage():
    class Flaky:
        def __init__(self):
            self.inner = Judge()
            self.n = 0

        async def complete(self, request):
            self.n += 1
            if self.n in (1, 2, 3):
                raise JudgeParseError("garbled")
            return await self.inner.complete(request)

    outcome = await run_calibration(CHECK, Flaky(), split="blind")
    assert outcome.result.n_unscored == 3
    assert outcome.result.n == len(BLIND) - 3
    gate = evaluate_gate(outcome.result, None, check=CHECK, split="blind", gold_version="x")
    assert not gate.passed and any("coverage too low" in r for r in gate.reasons)


@pytest.mark.unit
async def test_replay_refuses_unexpected_models():
    cas = build_full_cassette(CHECK)  # demo-heuristic-judge entries
    client = ReplayModelClient(cas, strict=True, expected_models={"claude-sonnet-5"})
    with pytest.raises(ProvenanceMismatch):
        await run_calibration(CHECK, client, split="blind")


@pytest.mark.unit
def test_provenance_flags_demo_and_mixed():
    cas = build_full_cassette(CHECK)
    assert cassette_provenance(cas).demonstration
    key = next(iter(cas.entries))
    cas.entries[key] = {**cas.entries[key], "model": "claude-sonnet-5"}
    prov = cassette_provenance(cas)
    assert prov.mixed and prov.demonstration


@pytest.mark.integration
def test_prove_labels_real_recordings_as_real(tmp_path, monkeypatch):
    import asyncio

    import fusion_first.cli
    from fusion_first.cli import main

    report = asyncio.run(record_gold_cassette_live(
        CHECK, Judge(), splits=("dev", "blind"), include_probes=True, path=tmp_path / f"{CHECK}.v1.json",
    ))
    assert report.ok
    monkeypatch.setattr(fusion_first.cli, "CASSETTE_DIR", tmp_path)
    out = tmp_path / "card.json"
    assert main(["prove", "--check", CHECK, "--json", str(out)]) == 0
    card = json.loads(out.read_text(encoding="utf-8"))
    assert card["demonstration"] is False
    assert card["judge_model"] == "claude-sonnet-5"
