"""Held-out integrity: seal blind splits, fingerprint the judge prompt and remedies, count burns.

WHY: a blind split proves judge accuracy only while two things stay true.

1. Nobody edited its rows after it was sealed (relabeling a hard case, dropping a miss, moving a row
   to dev). `compute_seal` records a sha256 per blind row; `verify_seal` reports every changed,
   missing, or added id — so an edit can't hide inside a "no functional change" commit.
2. It hasn't been used to TUNE the judge. Each time a new judge prompt is scored on the blind set
   we learn a little about it; iterate enough and it is a dev set wearing a blind label. The
   `BlindLedger` records which judge-prompt hashes were evaluated on which blind set and declares it
   burned once 3 DISTINCT prompts have seen it (re-running the same prompt leaks nothing new).

`judge_prompt_hash` / `remedies_hash` are the fingerprints those records (and report cards) carry,
so "which judge / which fix produced this number" is answerable from a hash alone.

Pure and offline: stdlib + fusion modules only. Writes are atomic (temp file + os.replace).
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


# ------------------------------------------------------------------ canonical hashing


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def row_hash(row: dict) -> str:
    """sha256 hex of the row's canonical JSON (sorted keys, no whitespace, UTF-8 not escaped), so
    the hash depends only on content, never on key order or file formatting."""
    return _sha256(_canonical(row))


def compute_seal(rows: Iterable[dict], split: str = "blind") -> dict[str, str]:
    """{row id: row_hash} for every row whose 'split' equals `split`. Fails on a missing or
    duplicate id: an ambiguous seal could let a tampered row hide behind its twin."""
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
    """One sha256 over the whole seal (order-independent): a stable id for 'this exact blind
    set', suitable as a BlindLedger dataset_id or a report-card provenance field."""
    return _sha256(_canonical(dict(seal)))


def verify_seal(
    rows: Iterable[dict], seal: Mapping[str, str], split: str = "blind"
) -> dict[str, list[str]]:
    """Compare current rows against a seal. `changed`: same id, different content; `missing`:
    sealed but no longer in the split (deleted, or moved out); `added`: in the split but never
    sealed. All three empty means the held-out set is exactly what was sealed."""
    current = compute_seal(rows, split=split)
    return {
        "changed": sorted(k for k in current.keys() & seal.keys() if current[k] != seal[k]),
        "missing": sorted(seal.keys() - current.keys()),
        "added": sorted(current.keys() - seal.keys()),
    }


# ------------------------------------------------------------------ seal files


def _atomic_write_json(path: pathlib.Path, doc: object) -> None:
    """Write JSON via a temp file in the same directory + os.replace, so a crash (or a concurrent
    reader) never sees a half-written seal or ledger."""
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
    """Persist a seal with free-form `meta` (dataset, split, gold version, who/why) and a digest
    that `load_seal` re-checks."""
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
        # The seal itself was edited (e.g. a row hash 'updated' to match an edited row). Committing
        # the seal to git is the real tamper evidence; this catches the careless case loudly.
        raise ValueError(f"seal file {p} digest mismatch: the seal was modified after writing")
    return doc


def load_seal(path: str | os.PathLike) -> dict[str, str]:
    """The {row id: hash} mapping from a seal file (ready for `verify_seal`). Raises ValueError on
    unreadable JSON, a malformed file, or a digest mismatch: a seal that can't be trusted is
    never treated as 'intact'."""
    return dict(_load_seal_doc(path)["rows"])


def load_seal_meta(path: str | os.PathLike) -> dict:
    """The `meta` block written with the seal (same integrity checks as `load_seal`)."""
    meta = _load_seal_doc(path).get("meta") or {}
    return dict(meta) if isinstance(meta, dict) else {}


# ------------------------------------------------------------------ fingerprints


def judge_prompt_hash(rubric: Rubric | str) -> str:
    """First 16 hex of sha256(build_system_prompt(rubric)). Accepts a Rubric or a check name. Any
    wording change to the judge's instructions or criteria gives a new hash, which is exactly the
    unit the BlindLedger counts."""
    if isinstance(rubric, str):
        rubric = get_rubric(rubric)
    return _sha256(build_system_prompt(rubric).encode("utf-8"))[:16]


def remedies_hash() -> str:
    """sha256 over every registered remedy (check, title, summary, rules) plus the rendered guard
    block, so it changes whenever any remedy text (or the block markers) changes. Read at call
    time from fusion_first.engine.fixes.REMEDIES, never cached."""
    remedies = {k: dataclasses.asdict(r) for k, r in sorted(fixes.REMEDIES.items())}
    block = fixes.guard_block(sorted(fixes.REMEDIES))
    return _sha256(_canonical({"remedies": remedies, "guard_block": block}))


# ------------------------------------------------------------------ burn ledger


def _require(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


class BlindLedger:
    """Append-only record of which judge prompts were evaluated on which blind set.

    The file is re-read on every call (so separate instances on one path agree) and rewritten
    atomically. A corrupt or unreadable ledger raises instead of being reset: silently starting a
    fresh ledger would 'un-burn' a burned blind set. Single-writer: concurrent writers could lose
    an entry (never corrupt the file)."""

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
        """Log one evaluation of `judge_prompt_hash` on blind set `dataset_id`; returns the
        entry. Recording is allowed after a burn (the log stays truthful); callers gate on
        `burned()`."""
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
        """Every recorded use of `dataset_id`, oldest first (copies)."""
        return [dict(u) for u in self._load() if u.get("dataset_id") == dataset_id]

    def distinct_hashes(self, dataset_id: str) -> list[str]:
        """Distinct judge prompt hashes evaluated on `dataset_id`, in first-use order."""
        seen: dict[str, None] = {}
        for u in self.uses(dataset_id):
            seen.setdefault(str(u.get("judge_prompt_hash", "")), None)
        return list(seen)

    def burned(self, dataset_id: str, max_distinct_hashes: int = DEFAULT_BURN_AT) -> bool:
        """True once >= `max_distinct_hashes` DISTINCT judge prompts have been evaluated on this
        blind set: its numbers can no longer be reported as held-out."""
        if max_distinct_hashes < 1:
            raise ValueError("max_distinct_hashes must be >= 1")
        return len(self.distinct_hashes(dataset_id)) >= max_distinct_hashes
