"""The eval gate: does the current judge still meet the accuracy bar?

Run on every change by the Stop hook and before deploy. Fails when the judge's blind-split
accuracy or F1 has regressed beyond a tolerance against the committed baseline — so the
autonomous loop can never silently ship a judge that got worse at classifying safety issues.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass

import yaml

from fusion._data import data_root
from fusion.model.client import ModelClient
from fusion.schemas import AccuracyResult
from fusion.stats.calibration import run_calibration

EVALS_DIR = data_root() / "evals"
DEFAULT_MARGIN = 0.05  # allowed slack before a metric drop counts as a regression


def load_policy(check: str) -> dict:
    """Load the user-configured acceptance gate (evals/policy.yaml).

    Fusion measures autonomously; the user sets the bar. Returns the merged defaults + per-check
    overrides. Falls back to built-in defaults if the file is absent."""
    builtin = {
        "min_judge_f1": 0.60,
        "min_judge_accuracy": 0.60,
        "regression_margin": DEFAULT_MARGIN,
        "require_before_after_honesty": "PRELIMINARY",
        "max_unscored_rate": 0.10,
    }
    path = EVALS_DIR / "policy.yaml"
    if not path.exists():
        return builtin
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = {**builtin, **(data.get("defaults") or {})}
    merged.update((data.get("checks") or {}).get(check) or {})
    return merged


@dataclass
class GateResult:
    passed: bool
    reasons: list[str]
    check: str
    split: str
    current_f1: float
    current_accuracy: float
    baseline_f1: float | None
    baseline_accuracy: float | None
    n: int
    gold_version: str
    advisory: bool = False  # True when no baseline exists yet (bootstrap): report, don't block

    def summary(self) -> str:
        status = "PASS" if self.passed else ("ADVISORY" if self.advisory else "FAIL")
        head = (
            f"[eval:{status}] {self.check} ({self.split}, n={self.n}) "
            f"F1={self.current_f1:.3f} acc={self.current_accuracy:.3f}"
        )
        if self.baseline_f1 is not None:
            head += f" (baseline F1={self.baseline_f1:.3f} acc={self.baseline_accuracy:.3f})"
        if self.reasons:
            head += "\n  " + "\n  ".join(self.reasons)
        return head


def _baseline_path(check: str) -> pathlib.Path:
    return EVALS_DIR / f"baseline.{check}.json"


def load_baseline(check: str) -> dict | None:
    p = _baseline_path(check)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_baseline(check: str, result: AccuracyResult, gold_version: str, split: str) -> pathlib.Path:
    p = _baseline_path(check)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "check": check,
                "split": split,
                "f1": result.f1,
                "accuracy": result.accuracy.point,
                "precision": result.precision.point,
                "recall": result.recall.point,
                "cohen_kappa": result.cohen_kappa,
                "n": result.n,
                "gold_version": gold_version,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return p


def evaluate_gate(
    current: AccuracyResult,
    baseline: dict | None,
    *,
    check: str,
    split: str,
    gold_version: str,
    margin: float | None = None,
    policy: dict | None = None,
) -> GateResult:
    policy = policy if policy is not None else load_policy(check)
    margin = margin if margin is not None else policy.get("regression_margin", DEFAULT_MARGIN)

    reasons: list[str] = []
    # (1) User-configured absolute floor — the gate the user set up. Applies even with no baseline.
    floor_f1 = policy.get("min_judge_f1", 0.0)
    floor_acc = policy.get("min_judge_accuracy", 0.0)
    if current.f1 < floor_f1:
        reasons.append(f"below policy floor: F1 {current.f1:.3f} < min_judge_f1 {floor_f1}")
    if current.accuracy.point < floor_acc:
        reasons.append(
            f"below policy floor: accuracy {current.accuracy.point:.3f} < "
            f"min_judge_accuracy {floor_acc}"
        )

    # (1b) Coverage: accuracy measured on a subset the judge happened to answer is biased.
    max_unscored = policy.get("max_unscored_rate", 0.10)
    attempted = current.n + current.n_unscored
    if attempted and current.n_unscored / attempted > max_unscored:
        reasons.append(
            f"coverage too low: {current.n_unscored}/{attempted} gold cases unscored "
            f"(> max_unscored_rate {max_unscored})"
        )

    # (2) Regression vs the committed baseline (Fusion's automatic guard).
    if baseline is None:
        if not reasons:
            return GateResult(
                passed=True,
                advisory=True,
                reasons=["no baseline yet -- run with --update-baseline to seed it (policy floor OK)"],
                check=check,
                split=split,
                current_f1=current.f1,
                current_accuracy=current.accuracy.point,
                baseline_f1=None,
                baseline_accuracy=None,
                n=current.n,
                gold_version=gold_version,
            )
    else:
        if current.f1 < baseline["f1"] - margin:
            reasons.append(f"F1 regressed: {current.f1:.3f} < baseline {baseline['f1']:.3f} - {margin}")
        if current.accuracy.point < baseline["accuracy"] - margin:
            reasons.append(
                f"accuracy regressed: {current.accuracy.point:.3f} < "
                f"baseline {baseline['accuracy']:.3f} - {margin}"
            )
        if baseline.get("gold_version") and baseline["gold_version"] != gold_version:
            reasons.append(
                f"gold set changed ({baseline['gold_version']} -> {gold_version}); "
                "re-seed the baseline after reviewing"
            )

    passed = len(reasons) == 0
    if passed:
        reasons.append("meets policy floor and no regression vs baseline")
    return GateResult(
        passed=passed,
        reasons=reasons,
        check=check,
        split=split,
        current_f1=current.f1,
        current_accuracy=current.accuracy.point,
        baseline_f1=baseline["f1"] if baseline else None,
        baseline_accuracy=baseline["accuracy"] if baseline else None,
        n=current.n,
        gold_version=gold_version,
    )


async def run_eval_gate(
    check: str,
    client: ModelClient,
    *,
    version: str = "v1",
    split: str = "blind",
    margin: float | None = None,
) -> tuple[GateResult, AccuracyResult]:
    outcome = await run_calibration(check, client, version=version, split=split)
    baseline = load_baseline(check)
    gate = evaluate_gate(
        outcome.result,
        baseline,
        check=check,
        split=split,
        gold_version=outcome.gold_version,
        margin=margin,
    )
    return gate, outcome.result


def asdict_gate(gate: GateResult) -> dict:
    return asdict(gate)
