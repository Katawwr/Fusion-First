"""Record a demo cassette for a gold set using the heuristic stand-in judge.

The cassette is keyed by the *real* Judge request hash, so replaying it drives the exact
production Judge code path (prompt build + structured parse + criteria-derived verdict).
Swapping the heuristic for a live Claude client here is the only change needed for real numbers.
"""

from __future__ import annotations

import json
import pathlib

from fusion._data import data_root
from fusion.goldset import load_gold
from fusion.judge.judge import Judge
from fusion.judge.rubric import get_rubric
from fusion.model.providers import demo_detectors  # noqa: F401  (registers agentic-check detectors)
from fusion.model.providers.heuristic import heuristic_verdict_json
from fusion.model.replay import Cassette, ReplayModelClient
from fusion.schemas import Trajectory

CASSETTE_DIR = data_root() / "cassettes"


def _request_builder() -> Judge:
    # A Judge whose client is never called here — used only to build request cache keys.
    return Judge(ReplayModelClient(Cassette(), strict=False))


def build_gold_cassette(check: str, version: str = "v1") -> Cassette:
    rubric = get_rubric(check)
    judge = _request_builder()
    cassette = Cassette()
    for case in load_gold(check, version):
        req = judge._build_request(case.trajectory, rubric)
        payload = json.dumps(heuristic_verdict_json(case.trajectory, rubric))
        from fusion.model.client import ModelResponse

        cassette.put(req.cache_key(), ModelResponse(text=payload, model="demo-heuristic-judge"))
    return cassette


def build_trajectory_cassette(trajectories: list[Trajectory], check: str) -> Cassette:
    """Record heuristic verdicts for an arbitrary set of trajectories (used by Bar B probes)."""
    rubric = get_rubric(check)
    judge = _request_builder()
    cassette = Cassette()
    from fusion.model.client import ModelResponse

    for traj in trajectories:
        req = judge._build_request(traj, rubric)
        payload = json.dumps(heuristic_verdict_json(traj, rubric))
        cassette.put(req.cache_key(), ModelResponse(text=payload, model="demo-heuristic-judge"))
    return cassette


def build_full_cassette(check: str, version: str = "v1") -> Cassette:
    """One cassette covering both the gold set (Bar A) and the paired probes (Bar B)."""
    from fusion.goldset import load_probes

    cassette = build_gold_cassette(check, version)
    probe_trajs: list[Trajectory] = []
    for probe in load_probes(check, version):
        probe_trajs.append(probe["baseline"])
        probe_trajs.append(probe["hardened"])
    probe_cas = build_trajectory_cassette(probe_trajs, check)
    cassette.entries.update(probe_cas.entries)
    return cassette


def write_full_cassette(check: str, version: str = "v1") -> pathlib.Path:
    cassette = build_full_cassette(check, version)
    path = CASSETTE_DIR / f"{check}.{version}.json"
    cassette.save(path)
    return path


async def record_gold_cassette_live(
    check: str,
    live_judge,
    *,
    version: str = "v1",
    splits: tuple[str, ...] = ("dev", "blind"),
    include_probes: bool = True,
    concurrency: int = 4,
) -> Cassette:
    """Record REAL judge verdicts over a check's gold set (and optionally its probe arms) into a
    cassette keyed the same way the offline gate replays it.

    The recorder wraps `live_judge` behind a DEFAULT `Judge` (model_id unset), so the request cache
    keys are byte-identical to the ones `fusion eval`/`prove` look up — the recorded cassette is a
    drop-in replacement for the heuristic one, with `model` != 'demo-heuristic-judge'. This is the
    ~10-line seam that turns the offline gate from a demonstration into a real measurement."""
    import asyncio

    from fusion.goldset import load_gold, load_probes
    from fusion.model.replay import RecordModelClient

    rubric = get_rubric(check)
    cassette = Cassette()
    judge = Judge(RecordModelClient(live_judge, cassette))  # default model_id -> request model_id=None

    trajectories: list[Trajectory] = [
        c.trajectory for c in load_gold(check, version) if c.split in splits
    ]
    if include_probes:
        for probe in load_probes(check, version):
            trajectories.append(probe["baseline"])
            trajectories.append(probe["hardened"])

    sem = asyncio.Semaphore(concurrency)

    async def _one(traj: Trajectory) -> None:
        async with sem:
            await judge.evaluate(traj, rubric)  # RecordModelClient captures the response by cache_key

    await asyncio.gather(*(_one(t) for t in trajectories))
    return cassette
