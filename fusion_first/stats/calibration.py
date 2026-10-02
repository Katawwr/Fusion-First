"""Bar A harness: judge vs oracle on the gold set, on the held-out `blind` split by default (the dev
split is where prompts are tuned, so reporting on it would overstate accuracy).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fusion_first.errors import classify, isolatable
from fusion_first.goldset import gold_version_hash, load_gold
from fusion_first.judge.judge import Judge
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.client import ModelClient
from fusion_first.schemas import AccuracyResult
from fusion_first.stats.metrics import accuracy_result


@dataclass
class CalibrationOutcome:
    result: AccuracyResult
    check: str
    split: str
    gold_version: str
    per_case: list[tuple[str, bool, bool]]  # (case_id, oracle_is_issue, judge_is_issue)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (case_id, ErrorKind) unscored


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
    errors: list[tuple[str, str]] = []
    for case in cases:
        try:
            verdict = await judge.evaluate(case.trajectory, rubric)
        except Exception as exc:  # noqa: BLE001
            if isolatable(exc):
                errors.append((case.id, classify(exc).value))
                continue
            raise
        y_true.append(case.oracle.is_issue)
        y_pred.append(verdict.is_issue)
        per_case.append((case.id, case.oracle.is_issue, verdict.is_issue))

    if not per_case:
        raise ValueError(f"no gold case could be scored for check={check} split={split}: {errors[:3]}")
    label_source = cases[0].oracle.source
    result = accuracy_result(y_true, y_pred, label_source=label_source)
    result = result.model_copy(update={"n_unscored": len(errors)})
    return CalibrationOutcome(
        result=result,
        check=check,
        split=split or "all",
        gold_version=gold_version_hash(check, version),
        per_case=per_case,
        errors=errors,
    )
