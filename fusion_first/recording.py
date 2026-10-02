"""Record judge cassettes: heuristic stand-in (demo) or live, keyed by the real Judge request hash so
replay drives the production Judge code path.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from fusion_first._data import data_root
from fusion_first.goldset import load_gold
from fusion_first.judge.judge import Judge
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.providers import (
    demo_detectors,  # noqa: F401  (registers agentic-check detectors)
)
from fusion_first.model.providers.heuristic import heuristic_verdict_json
from fusion_first.model.replay import Cassette, ReplayModelClient
from fusion_first.schemas import Trajectory

CASSETTE_DIR = data_root() / "cassettes"


def _request_builder() -> Judge:
    # Never called: used only to build request cache keys.
    return Judge(ReplayModelClient(Cassette(), strict=False))


def build_gold_cassette(check: str, version: str = "v1") -> Cassette:
    rubric = get_rubric(check)
    judge = _request_builder()
    cassette = Cassette()
    for case in load_gold(check, version):
        req = judge._build_request(case.trajectory, rubric)
        payload = json.dumps(heuristic_verdict_json(case.trajectory, rubric))
        from fusion_first.model.client import ModelResponse

        cassette.put(req.cache_key(), ModelResponse(text=payload, model="demo-heuristic-judge"))
    return cassette


def build_trajectory_cassette(trajectories: list[Trajectory], check: str) -> Cassette:
    rubric = get_rubric(check)
    judge = _request_builder()
    cassette = Cassette()
    from fusion_first.model.client import ModelResponse

    for traj in trajectories:
        req = judge._build_request(traj, rubric)
        payload = json.dumps(heuristic_verdict_json(traj, rubric))
        cassette.put(req.cache_key(), ModelResponse(text=payload, model="demo-heuristic-judge"))
    return cassette


def build_full_cassette(check: str, version: str = "v1") -> Cassette:
    """Gold set (Bar A) plus paired probes (Bar B)."""
    from fusion_first.goldset import load_probes

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


@dataclass
class RecordReport:
    """`aborted` is set when a run-level failure stopped the recording; progress so far is saved."""

    cassette: Cassette
    recorded: int = 0
    reused: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (case label, ErrorKind value)
    aborted: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failed and self.aborted is None


async def record_gold_cassette_live(
    check: str,
    live_judge,
    *,
    version: str = "v1",
    splits: tuple[str, ...] = ("dev", "blind"),
    include_probes: bool = True,
    concurrency: int = 4,
    path: str | pathlib.Path | None = None,
    resume: bool = True,
    every: int = 10,
) -> RecordReport:
    """Record real judge verdicts over a check's gold set (and probe arms) into a cassette.

    `live_judge` sits behind a default `Judge` (model_id unset) so cache keys match what `eval`/`prove`
    look up. Checkpointed every `every` answers; `resume` continues a real recording but never mixes
    in a demo cassette; one failed case is reported, a run-level failure saves and stops."""
    import asyncio

    from fusion_first.errors import classify, isolatable
    from fusion_first.goldset import load_gold, load_probes
    from fusion_first.model.replay import CheckpointingRecordClient, cassette_provenance

    rubric = get_rubric(check)
    cassette = Cassette.load(path) if (path is not None and resume) else Cassette()
    if cassette.entries and cassette_provenance(cassette).demonstration:
        cassette = Cassette()  # never mix stand-in verdicts into a real recording
    already = len(cassette)
    recorder = CheckpointingRecordClient(live_judge, cassette, path, every=every)
    judge = Judge(recorder)  # default model_id -> request model_id=None

    items: list[tuple[str, Trajectory]] = [
        (c.id, c.trajectory) for c in load_gold(check, version) if c.split in splits
    ]
    if include_probes:
        for probe in load_probes(check, version):
            items.append((f"{probe['id']}:baseline", probe["baseline"]))
            items.append((f"{probe['id']}:hardened", probe["hardened"]))

    report = RecordReport(cassette=cassette)
    sem = asyncio.Semaphore(concurrency)
    stop = asyncio.Event()  # set on a run-level failure: queued cases must not make more calls

    async def _one(label: str, traj: Trajectory) -> None:
        async with sem:
            if stop.is_set():
                return
            try:
                await judge.evaluate(traj, rubric)  # the recorder captures the raw answer by key
            except Exception as exc:  # noqa: BLE001  isolatable errors are per case
                if isolatable(exc):
                    report.failed.append((label, classify(exc).value))
                    return
                stop.set()
                raise

    tasks = [asyncio.create_task(_one(label, traj)) for label, traj in items]
    try:
        if tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            fatal = next((t.exception() for t in done if not t.cancelled() and t.exception()), None)
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if fatal is not None:
                report.aborted = f"{classify(fatal).value}: {fatal}"
    finally:
        recorder.flush()
    report.recorded = recorder.new_entries
    report.reused = min(already, len(cassette))
    return report
