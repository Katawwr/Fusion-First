"""A cassette recorded live through a default Judge (faked here) replays under run_calibration with zero
misses and carries a non-heuristic `model` field."""

from __future__ import annotations

import json

import pytest

from fusion_first.goldset import load_gold
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.client import ModelResponse
from fusion_first.model.replay import ReplayModelClient
from fusion_first.recording import record_gold_cassette_live
from fusion_first.stats.calibration import run_calibration

CHECK = "direct_prompt_injection"


class _FakeLiveJudge:
    """Emits all rubric criteria as not-violated (a valid, parseable verdict) tagged as a real model."""

    def __init__(self, check: str):
        self._ids = [c.id for c in get_rubric(check).criteria]

    async def complete(self, request):
        crit = [{"id": cid, "violated": False, "evidence": ""} for cid in self._ids]
        return ModelResponse(
            text=json.dumps({"criteria": crit, "rationale": "r", "confidence": 0.8}),
            model="claude-sonnet-5",
        )


@pytest.mark.integration
async def test_live_recorded_cassette_replays_with_zero_misses():
    report = await record_gold_cassette_live(
        CHECK, _FakeLiveJudge(CHECK), splits=("blind",), include_probes=False, concurrency=3
    )
    assert report.ok
    cass = report.cassette
    blind = [c for c in load_gold(CHECK) if c.split == "blind"]
    assert len(cass) == len(blind)  # one recorded verdict per blind gold case
    assert all(e["model"] == "claude-sonnet-5" for e in cass.entries.values())

    client = ReplayModelClient(cass, strict=True)
    outcome = await run_calibration(CHECK, client, split="blind")
    assert client.misses == []
    assert outcome.result.n == len(blind)
