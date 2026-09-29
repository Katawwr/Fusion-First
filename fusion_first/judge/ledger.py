"""The judge ledger: each judge backend's MEASURED accuracy, so every card can carry the Bar A of the
judge that actually graded it — never a stronger judge's numbers, never a claim.

An entry is keyed by (backend, model, check) plus a fingerprint of everything that changes the
judge's behaviour (the rubric's judge prompt and the judge code version). When the rubric or the
parser changes, the fingerprint changes and old entries stop matching automatically.

Qualification turns an entry into a trust decision (policy: evals/policy.yaml `judge_qualification`):
  QUALIFIED     — point floors met AND the Wilson lower bound of accuracy clears the pooled floor.
  PROVISIONAL   — point floors met but the sample is too small to clear the lower bound.
  UNQUALIFIED   — below a floor, or too many unscored cases: its grades must be withheld.
Stores: committed `evals/judges/` (maintainer-measured) and the user's `~/.fusion/ledger/`.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import tempfile
from dataclasses import asdict, dataclass

from fusion_first._data import data_root
from fusion_first.schemas import AccuracyResult

# Bump when the judge's parsing/verdict logic changes in a way that could change verdicts.
JUDGE_CODE_VERSION = "2026-09-26.strict-parse"

COMMITTED_DIR = data_root() / "evals" / "judges"

DEFAULT_QUALIFICATION = {
    "min_check_f1": 0.60,
    "min_accuracy_lcb": 0.60,
    "max_unscored_rate": 0.10,
}


class Qualification:
    QUALIFIED = "QUALIFIED"
    PROVISIONAL = "PROVISIONAL"
    UNQUALIFIED = "UNQUALIFIED"
    UNMEASURED = "UNMEASURED"


def user_ledger_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("FUSION_HOME", pathlib.Path.home() / ".fusion")) / "ledger"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "unknown"


def judge_fingerprint(backend: str, model_id: str, check: str) -> str:
    """Everything that changes this judge's verdicts: backend, model, the check's judge prompt, and
    the judge code version."""
    from fusion_first.judge.judge import build_system_prompt
    from fusion_first.judge.rubric import get_rubric

    prompt = build_system_prompt(get_rubric(check))
    blob = json.dumps(
        {"backend": backend, "model": model_id, "check": check, "prompt": prompt, "code": JUDGE_CODE_VERSION},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class LedgerEntry:
    backend: str
    model_id: str
    check: str
    fingerprint: str
    gold_version: str
    split: str
    accuracy: dict  # AccuracyResult.model_dump()
    measured_at: str  # ISO date, supplied by the caller (keeps this module deterministic)
    evidence: str = ""  # path of the replayable cassette the numbers came from
    label_tier: str = ""  # e.g. "in-house gold", "oracle", "external"

    @property
    def result(self) -> AccuracyResult:
        return AccuracyResult(**self.accuracy)


def _path(root: pathlib.Path, backend: str, model_id: str, check: str) -> pathlib.Path:
    return root / f"{_slug(backend)}__{_slug(model_id)}" / f"{check}.json"


def save_entry(entry: LedgerEntry, root: pathlib.Path | None = None) -> pathlib.Path:
    path = _path(root or user_ledger_dir(), entry.backend, entry.model_id, entry.check)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ledger.", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(asdict(entry), f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return path


def load_entry(
    backend: str, model_id: str, check: str, roots: list[pathlib.Path] | None = None
) -> LedgerEntry | None:
    """The newest matching entry whose fingerprint still matches the current judge (stale entries
    — from an older rubric or judge code — are ignored). User ledger wins over committed."""
    fp = judge_fingerprint(backend, model_id, check)
    for root in roots if roots is not None else [user_ledger_dir(), COMMITTED_DIR]:
        path = _path(root, backend, model_id, check)
        if not path.is_file():
            continue
        try:
            entry = LedgerEntry(**json.loads(path.read_text(encoding="utf-8")))
        except (TypeError, ValueError):
            continue
        if entry.fingerprint == fp:
            return entry
    return None


def qualify(acc: AccuracyResult | None, policy: dict | None = None) -> tuple[str, list[str]]:
    """Turn a measured accuracy into a trust decision + reasons."""
    if acc is None:
        return Qualification.UNMEASURED, ["this judge has not been measured against the gold set"]
    p = {**DEFAULT_QUALIFICATION, **(policy or {})}
    reasons: list[str] = []
    attempted = acc.n + acc.n_unscored
    if attempted and acc.n_unscored / attempted > p["max_unscored_rate"]:
        reasons.append(f"{acc.n_unscored}/{attempted} gold cases unscored (> {p['max_unscored_rate']:.0%})")
    if acc.f1 < p["min_check_f1"]:
        reasons.append(f"F1 {acc.f1:.2f} below the {p['min_check_f1']:.2f} floor")
    if reasons:
        return Qualification.UNQUALIFIED, reasons
    if acc.accuracy.low < p["min_accuracy_lcb"]:
        return Qualification.PROVISIONAL, [
            f"accuracy {acc.accuracy.point:.0%} but its 95% lower bound {acc.accuracy.low:.0%} is "
            f"below {p['min_accuracy_lcb']:.0%} (n={acc.n} is small)"
        ]
    return Qualification.QUALIFIED, []


def ledger_accuracy_provider(backend: str, model_id: str, roots: list[pathlib.Path] | None = None):
    """An AccuracyProvider for run_user_scan: Bar A of THIS judge from the ledger, or a note."""

    async def provider(check: str, judge_id: str):
        entry = load_entry(backend, model_id, check, roots)
        if entry is None:
            return None, "", (
                f"Not yet measured for judge {model_id} via {backend} — run "
                f"`fusion judge qualify` to measure it against the labelled gold set."
            ), ""
        status, reasons = qualify(entry.result)
        note = "" if status == Qualification.QUALIFIED else f"{status}: " + "; ".join(reasons)
        return entry.result, entry.gold_version, note, f"ledger ({entry.label_tier or 'gold'}, {entry.measured_at})"

    return provider
