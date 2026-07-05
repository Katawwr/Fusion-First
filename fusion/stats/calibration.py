"""Bar A harness: run the judge over a labeled gold set and measure agreement with the oracle.

Reports on the held-out `blind` split by default (the dev split is where thresholds/prompts are
tuned; reporting on it would overstate accuracy). Fully offline when given a ReplayModelClient.
"""

from __future__ import annotations

from dataclasses import dataclass

from fusion.goldset import gold_version_hash, load_gold
from fusion.judge.judge import Judge
from fusion.judge.rubric import get_rubric
from fusion.model.client import ModelClient
from fusion.schemas import AccuracyResult
from fusion.stats.metrics import accuracy_result


@dataclass
class CalibrationOutcome:
    result: AccuracyResult
    check: str
    split: str
    gold_version: str
    per_case: list[tuple[str, bool, bool]]  # (case_id, oracle_is_issue, judge_is_issue)


async def run_calibration(
    check: str,
    client: ModelClient,
    version: str = "v1",
    split: str | None = "blind",
) -> CalibrationOutcome:
    rubric = get_rubric(check)
    judge = Judge(client)
    cases = [c for c in load_gold(check, version) if split is None or c.split == split]
    if not cases:
        raise ValueError(f"no gold cases for check={check} split={split}")

    y_true: list[bool] = []
    y_pred: list[bool] = []
    per_case: list[tuple[str, bool, bool]] = []
    for case in cases:
        verdict = await judge.evaluate(case.trajectory, rubric)
        y_true.append(case.oracle.is_issue)
        y_pred.append(verdict.is_issue)
        per_case.append((case.id, case.oracle.is_issue, verdict.is_issue))

    label_source = cases[0].oracle.source
    result = accuracy_result(y_true, y_pred, label_source=label_source)
    return CalibrationOutcome(
        result=result,
        check=check,
        split=split or "all",
        gold_version=gold_version_hash(check, version),
        per_case=per_case,
    )
