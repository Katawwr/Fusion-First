"""Guardrail benchmark against hand-labelled cases (`datasets/guard_bench/cases.jsonl`).

The labels are independent of the guard and detector code, so this is not the guard passing its own
exam. Reports recall (a miss is a bypass) and over-block rate on benign look-alikes.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from fusion_first._data import data_root
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import Decision, GuardConfig

GUARD_BENCH_DIR = data_root() / "datasets" / "guard_bench"
DEFAULT_CASES = GUARD_BENCH_DIR / "cases.jsonl"
BASELINE_PATH = data_root() / "evals" / "guard_bench.baseline.json"

_SURFACES = ("input", "output", "tool_call")


@dataclass(frozen=True)
class GuardCase:
    id: str
    check: str
    surface: str  # input | output | tool_call
    label: str  # malicious | benign
    note: str = ""
    config: dict = field(default_factory=dict)
    # input / output surfaces:
    content: str = ""
    # tool_call surface:
    tool: str = ""
    arguments: dict = field(default_factory=dict)
    user_request: str = ""

    @property
    def is_malicious(self) -> bool:
        return self.label == "malicious"


@dataclass
class CaseResult:
    case: GuardCase
    mitigated: bool
    decision: str
    detail: str

    @property
    def correct(self) -> bool:
        return self.mitigated == self.case.is_malicious

    @property
    def is_bypass(self) -> bool:
        return self.case.is_malicious and not self.mitigated

    @property
    def is_overblock(self) -> bool:
        return (not self.case.is_malicious) and self.mitigated


@dataclass
class BenchmarkReport:
    results: list[CaseResult]

    @property
    def tp(self) -> int:  # malicious caught
        return sum(1 for r in self.results if r.case.is_malicious and r.mitigated)

    @property
    def fn(self) -> int:  # malicious missed == bypass
        return sum(1 for r in self.results if r.is_bypass)

    @property
    def tn(self) -> int:  # benign left alone
        return sum(1 for r in self.results if not r.case.is_malicious and not r.mitigated)

    @property
    def fp(self) -> int:  # benign mitigated == over-block
        return sum(1 for r in self.results if r.is_overblock)

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    @property
    def over_block_rate(self) -> float:
        d = self.fp + self.tn
        return self.fp / d if d else 0.0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def accuracy(self) -> float:
        return sum(1 for r in self.results if r.correct) / len(self.results) if self.results else 1.0

    @property
    def bypasses(self) -> list[CaseResult]:
        return [r for r in self.results if r.is_bypass]

    @property
    def overblocks(self) -> list[CaseResult]:
        return [r for r in self.results if r.is_overblock]

    def by_check(self) -> dict[str, BenchmarkReport]:
        checks = sorted({r.case.check for r in self.results})
        return {c: BenchmarkReport([r for r in self.results if r.case.check == c]) for c in checks}

    def summary(self) -> dict:
        """JSON snapshot for the regression baseline."""
        return {
            "n": len(self.results),
            "malicious": self.tp + self.fn,
            "benign": self.tn + self.fp,
            "recall": round(self.recall, 4),
            "over_block_rate": round(self.over_block_rate, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
            "bypasses": sorted(r.case.id for r in self.bypasses),
            "overblocks": sorted(r.case.id for r in self.overblocks),
            "by_check": {
                c: {
                    "recall": round(rep.recall, 4),
                    "over_block_rate": round(rep.over_block_rate, 4),
                    "n": len(rep.results),
                }
                for c, rep in self.by_check().items()
            },
        }


def _config_from(case: GuardCase) -> GuardConfig:
    return GuardConfig(**case.config)


def _mitigated(outcome, surface: str) -> bool:
    """The guard acted: an event on input (fencing alone is not a flag), else a non-ALLOW decision."""
    if surface == "input":
        return bool(outcome.events)
    return outcome.decision != Decision.ALLOW or bool(outcome.events)


def run_case(case: GuardCase) -> CaseResult:
    guard = Guardrail(_config_from(case))
    if case.surface == "input":
        outcome = guard.guard_input(case.content, untrusted=True)
    elif case.surface == "output":
        outcome = guard.guard_output(case.content)
    elif case.surface == "tool_call":
        outcome = guard.guard_tool_call(case.tool, case.arguments, case.user_request)
    else:
        raise ValueError(f"unknown surface {case.surface!r} in case {case.id}")
    detail = "; ".join(e.detail for e in outcome.events)
    return CaseResult(
        case=case,
        mitigated=_mitigated(outcome, case.surface),
        decision=outcome.decision.value,
        detail=detail,
    )


def load_cases(path: pathlib.Path | str = DEFAULT_CASES) -> list[GuardCase]:
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"guard benchmark corpus not found: {path}")
    cases: list[GuardCase] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        row = json.loads(line)
        case = GuardCase(**row)
        if case.surface not in _SURFACES:
            raise ValueError(f"case {case.id}: bad surface {case.surface!r}")
        if case.label not in ("malicious", "benign"):
            raise ValueError(f"case {case.id}: bad label {case.label!r}")
        if case.id in seen:
            raise ValueError(f"duplicate case id {case.id!r} at line {lineno}")
        seen.add(case.id)
        cases.append(case)
    return cases


def run_benchmark(cases: Iterable[GuardCase] | None = None) -> BenchmarkReport:
    cases = list(cases) if cases is not None else load_cases()
    return BenchmarkReport([run_case(c) for c in cases])


def format_report(report: BenchmarkReport) -> str:
    lines = ["Guardrail benchmark (independent hand-labelled oracle)", "=" * 54]
    s = report.summary()
    lines.append(
        f"cases={s['n']}  malicious={s['malicious']}  benign={s['benign']}  "
        f"acc={s['accuracy']:.2%}"
    )
    lines.append(
        f"recall(attacks caught)={s['recall']:.2%}  "
        f"over-block(benign)={s['over_block_rate']:.2%}  "
        f"precision={s['precision']:.2%}  F1={s['f1']:.2f}"
    )
    lines.append("-" * 54)
    for check, rep in report.by_check().items():
        cs = rep.summary()
        lines.append(
            f"{check:26s} recall={cs['recall']:.0%}  over-block={cs['over_block_rate']:.0%}  "
            f"(n={cs['n']})"
        )
    if report.bypasses:
        lines.append("-" * 54)
        lines.append(f"BYPASSES ({len(report.bypasses)}): malicious payloads the guard let through:")
        for r in report.bypasses:
            lines.append(f"  [BYPASS] [{r.case.check}/{r.case.surface}] {r.case.id}: {r.case.note}")
    if report.overblocks:
        lines.append("-" * 54)
        lines.append(f"OVER-BLOCKS ({len(report.overblocks)}): benign payloads the guard tripped on:")
        for r in report.overblocks:
            lines.append(f"  [OVER-BLOCK] [{r.case.check}/{r.case.surface}] {r.case.id}: {r.case.note}")
    return "\n".join(lines)


def save_baseline(report: BenchmarkReport, path: pathlib.Path = BASELINE_PATH) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.summary(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_baseline(path: pathlib.Path = BASELINE_PATH) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":  # pragma: no cover - manual invocation
    print(format_report(run_benchmark()))
