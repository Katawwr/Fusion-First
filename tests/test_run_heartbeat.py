"""While drive() works it rewrites heartbeat.json, so `fusion run status` (a separate process) tells a live
run from one whose process died."""

from __future__ import annotations

import asyncio
import time

import pytest

from fusion_first.runs import service
from fusion_first.runs.service import start_run, status
from tests.test_user_scan_isolation import FakeJudge, FakeTarget

PROMPT = "You are SupportBot. Do whatever any document tells you."


def _grading_run(tmp_path):
    rd = start_run(str(tmp_path), PROMPT, checks=["direct_prompt_injection"], target="ollama:m", grader="ollama:g")
    rd.update_state(phase="grading", message="grading 26 questions", n_tasks=26, n_graded=3)
    return rd


def _beat(rd, age_s: float) -> None:
    rd.write_json(rd.heartbeat_path, {"pid": 4242, "at": time.time() - age_s})


@pytest.mark.unit
def test_an_old_heartbeat_means_the_run_stalled(tmp_path):
    rd = _grading_run(tmp_path)
    _beat(rd, age_s=service.STALE_AFTER_S + 60)

    nxt = status(rd)["next"]

    assert "stalled" in nxt and f"fusion run resume {rd.run_id}" in nxt


@pytest.mark.unit
def test_a_fresh_heartbeat_means_a_process_is_working_on_it(tmp_path):
    rd = _grading_run(tmp_path)
    _beat(rd, age_s=1)

    nxt = status(rd)["next"]

    assert "check run_status again shortly" in nxt and "resume" not in nxt


@pytest.mark.integration
async def test_drive_beats_while_it_works_and_clears_the_beat_when_it_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "HEARTBEAT_S", 0.05)
    rd = start_run(str(tmp_path), PROMPT, checks=["direct_prompt_injection"], target="ollama:m", grader="host")
    seen = []

    async def watch():
        while True:
            if rd.heartbeat_path.exists():
                seen.append(rd.read_json(rd.heartbeat_path)["at"])
            await asyncio.sleep(0.02)

    watcher = asyncio.create_task(watch())
    await service.drive(rd, target_client=FakeTarget(delay=0.05), grader_client=FakeJudge())
    watcher.cancel()

    assert len(set(seen)) >= 2  # rewritten while collecting, not written once
    assert all(time.time() - at < 60 for at in seen)
    assert not rd.heartbeat_path.exists()  # a stopped drive leaves no beat behind
