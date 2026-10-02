"""Held-out integrity: seal blind splits, fingerprint the judge prompt and remedies, count burns.

A blind split stays blind only while its rows are unedited (`compute_seal` / `verify_seal`) and it
has not been used to tune the judge (`BlindLedger`: burned once 3 distinct judge prompts have seen it).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import tempfile
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from fusion_first.engine import fixes
from fusion_first.judge.judge import build_system_prompt
from fusion_first.judge.rubric import Rubric, get_rubric

SEAL_FORMAT = "fusion.seal/v1"
LEDGER_FORMAT = "fusion.blind_ledger/v1"
DEFAULT_BURN_AT = 3


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def row_hash(row: dict) -> str:
    """sha256 hex of the row's canonical JSON (independent of key order and formatting)."""
    return _sha256(_canonical(row))


def compute_seal(rows: Iterable[dict], split: str = "blind") -> dict[str, str]:
    """{row id: row_hash} for every row in `split`. Fails on a missing or duplicate id."""
    seal: dict[str, str] = {}
    for row in rows:
        if row.get("split") != split:
            continue
        rid = row.get("id")
        if not isinstance(rid, str) or not rid:
            raise ValueError(f"{split} row without a string 'id': {str(row)[:80]}")
        if rid in seal:
            raise ValueError(f"duplicate {split} row id '{rid}'")
        seal[rid] = row_hash(row)
    return seal


def seal_digest(seal: Mapping[str, str]) -> str:
    """One order-independent sha256 over the whole seal: a stable id for this exact blind set."""
    return _sha256(_canonical(dict(seal)))


def verify_seal(
    rows: Iterable[dict], seal: Mapping[str, str], split: str = "blind"
) -> dict[str, list[str]]:
    """Changed, missing and added ids versus the seal (all empty = intact)."""
    current = compute_seal(rows, split=split)
    return {
        "changed": sorted(k for k in current.keys() & seal.keys() if current[k] != seal[k]),
        "missing": sorted(seal.keys() - current.keys()),
        "added": sorted(current.keys() - seal.keys()),
    }


def _atomic_write_json(path: pathlib.Path, doc: object) -> None:
    """Atomic JSON write (temp file + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: pathlib.Path, what: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{what} {path} is not valid JSON: {e}") from e


def write_seal(
    path: str | os.PathLike, seal: Mapping[str, str], meta: Mapping | None = None
) -> None:
    """Persist a seal with free-form `meta` and a digest that `load_seal` re-checks."""
    rows = dict(sorted(seal.items()))
    doc = {
        "format": SEAL_FORMAT,
        "meta": dict(meta or {}),
        "n_rows": len(rows),
        "digest": seal_digest(rows),
        "rows": rows,
    }
    _atomic_write_json(pathlib.Path(path), doc)


def _load_seal_doc(path: str | os.PathLike) -> dict:
    p = pathlib.Path(path)
    doc = _read_json(p, "seal file")
    if not isinstance(doc, dict) or not isinstance(doc.get("rows"), dict):
        raise ValueError(f"seal file {p} has no 'rows' mapping")
    rows = doc["rows"]
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in rows.items()):
        raise ValueError(f"seal file {p} rows must map string ids to hex hashes")
    if doc.get("digest") != seal_digest(rows):
        # Git history is the real tamper evidence; this catches the careless edit loudly.
        raise ValueError(f"seal file {p} digest mismatch: the seal was modified after writing")
    return doc


def load_seal(path: str | os.PathLike) -> dict[str, str]:
    """The {row id: hash} mapping from a seal file; raises ValueError if it can't be trusted."""
    return dict(_load_seal_doc(path)["rows"])


def load_seal_meta(path: str | os.PathLike) -> dict:
    """The `meta` block written with the seal (same integrity checks as `load_seal`)."""
    meta = _load_seal_doc(path).get("meta") or {}
    return dict(meta) if isinstance(meta, dict) else {}


def judge_prompt_hash(rubric: Rubric | str) -> str:
    """First 16 hex of sha256 of the judge system prompt (the unit the BlindLedger counts)."""
    if isinstance(rubric, str):
        rubric = get_rubric(rubric)
    return _sha256(build_system_prompt(rubric).encode("utf-8"))[:16]


def remedies_hash() -> str:
    """sha256 over every registered remedy plus the rendered guard block."""
    remedies = {k: dataclasses.asdict(r) for k, r in sorted(fixes.REMEDIES.items())}
    block = fixes.guard_block(sorted(fixes.REMEDIES))
    return _sha256(_canonical({"remedies": remedies, "guard_block": block}))


def _require(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


class BlindLedger:
    """Append-only record of which judge prompts were evaluated on which blind set. A corrupt ledger
    raises instead of being reset (a fresh ledger would 'un-burn' a blind set). Single-writer."""

    def __init__(self, path: str | os.PathLike):
        self.path = pathlib.Path(path)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        doc = _read_json(self.path, "blind ledger")
        if not isinstance(doc, dict) or not isinstance(doc.get("uses"), list):
            raise ValueError(f"blind ledger {self.path} has no 'uses' list")
        uses = doc["uses"]
        if not all(isinstance(u, dict) for u in uses):
            raise ValueError(f"blind ledger {self.path} has a malformed entry")
        return uses

    def record_use(self, dataset_id: str, judge_prompt_hash: str, note: str = "") -> dict:
        """Log one evaluation (allowed after a burn; callers gate on `burned()`)."""
        entry = {
            "dataset_id": _require(dataset_id, "dataset_id"),
            "judge_prompt_hash": _require(judge_prompt_hash, "judge_prompt_hash"),
            "note": str(note or ""),
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        uses = self._load()
        uses.append(entry)
        _atomic_write_json(self.path, {"format": LEDGER_FORMAT, "uses": uses})
        return dict(entry)

    def uses(self, dataset_id: str) -> list[dict]:
        return [dict(u) for u in self._load() if u.get("dataset_id") == dataset_id]

    def distinct_hashes(self, dataset_id: str) -> list[str]:
        seen: dict[str, None] = {}
        for u in self.uses(dataset_id):
            seen.setdefault(str(u.get("judge_prompt_hash", "")), None)
        return list(seen)

    def burned(self, dataset_id: str, max_distinct_hashes: int = DEFAULT_BURN_AT) -> bool:
        """True once enough distinct judge prompts have seen this blind set to void it as held-out."""
        if max_distinct_hashes < 1:
            raise ValueError("max_distinct_hashes must be >= 1")
        return len(self.distinct_hashes(dataset_id)) >= max_distinct_hashes
