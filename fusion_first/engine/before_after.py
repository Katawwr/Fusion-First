"""Bar B runner: judge each paired probe's baseline and hardened trajectory, then run paired stats."""

from __future__ import annotations

from fusion_first.goldset import load_probes
from fusion_first.judge.judge import Judge
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.client import ModelClient
from fusion_first.schemas import BeforeAfterResult
from fusion_first.stats.paired import before_after


async def run_before_after(
    check: str,
    client: ModelClient,
    version: str = "v1",
    seed: int = 42,
) -> BeforeAfterResult:
    rubric = get_rubric(check)
    judge = Judge(client)
    probes = load_probes(check, version)

    baseline_fail: list[bool] = []
    hardened_fail: list[bool] = []
    for probe in probes:
        b = await judge.evaluate(probe["baseline"], rubric)
        h = await judge.evaluate(probe["hardened"], rubric)
        baseline_fail.append(b.is_issue)
        hardened_fail.append(h.is_issue)

    return before_after(baseline_fail, hardened_fail, seed=seed)
