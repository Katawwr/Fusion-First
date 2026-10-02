"""Resumable generation of evidence transcripts for the oracle experiments.

Each response is appended to a committed JSONL store as it arrives; a re-run skips what is recorded,
and a failed call is recorded as an error (retried next run, never scored).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass

from fusion_first.errors import isolatable
from fusion_first.model.client import ModelClient, ModelRequest, ModelRole
from fusion_first.validate.experiments import EvidenceItem

STORE_DIR_DEFAULT = "evals/validation/v1/transcripts"


@dataclass
class TranscriptRecord:
    experiment: str
    item_id: str
    model: str
    arm: str
    system_sha256: str  # sha256 of system + user (the full prompt), despite the historical name
    response: str | None
    error: str | None = None
    truncated: bool = False
    latency_s: float | None = None
    served_model: str | None = None
    seed: int | None = None
    max_tokens: int | None = None


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "-" for c in text)


class TranscriptStore:
    """Append-only JSONL files, one per (experiment, model). Last record per key wins."""

    def __init__(self, root: str | pathlib.Path):
        self.root = pathlib.Path(root)

    def path(self, experiment: str, model: str) -> pathlib.Path:
        return self.root / f"{experiment}__{_slug(model)}.jsonl"

    def load(self, experiment: str, model: str) -> dict[tuple[str, str], TranscriptRecord]:
        p = self.path(experiment, model)
        out: dict[tuple[str, str], TranscriptRecord] = {}
        if not p.is_file():
            return out
        text = p.read_text(encoding="utf-8")
        lines = text.split("\n")
        # An unterminated final line is a write in progress: skip it. A malformed complete line raises.
        complete = lines[:-1] if not text.endswith("\n") else lines
        for line in complete:
            if line.strip():
                rec = TranscriptRecord(**json.loads(line))
                out[(rec.item_id, rec.arm)] = rec
        return out

    def append(self, rec: TranscriptRecord) -> None:
        p = self.path(rec.experiment, rec.model)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(asdict(rec), ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def generate(
    plan: Iterable[tuple[str, EvidenceItem, str]],
    client_for: Callable[[str], ModelClient],
    store: TranscriptStore,
    *,
    max_tokens: int = 400,
    seed: int = 7,
    on_progress: Callable[[str], None] | None = None,
    stop_after: int | None = None,
    max_tokens_for: Callable[[EvidenceItem], int] | None = None,
) -> dict:
    """Run every (model, item, arm) not yet recorded successfully. Isolatable failures are recorded as
    errors; run-level failures (usage limit, budget, auth) propagate."""
    done_cache: dict[tuple[str, str], dict] = {}
    counts = {"generated": 0, "skipped": 0, "errored": 0}
    clients: dict[str, ModelClient] = {}
    for model, item, arm in plan:
        key = (item.experiment, model)
        if key not in done_cache:
            done_cache[key] = store.load(item.experiment, model)
        prior = done_cache[key].get((item.item_id, arm))
        system = item.system_for(arm)
        # Keyed on the full prompt: changing system or user regenerates.
        prompt_sha = _sha(system + "\n\x00\n" + item.user)
        if prior and prior.response is not None and prior.system_sha256 == prompt_sha:
            counts["skipped"] += 1
            continue
        if stop_after is not None and counts["generated"] + counts["errored"] >= stop_after:
            break
        client = clients.setdefault(model, client_for(model))
        cap = max_tokens_for(item) if max_tokens_for else max_tokens
        req = ModelRequest(
            role=ModelRole.TARGET, system=system, messages=[{"role": "user", "content": item.user}],
            max_tokens=cap, temperature=0.0, seed=seed, model_id=model,
        )
        started = time.monotonic()
        try:
            resp = await client.complete(req)
            rec = TranscriptRecord(
                experiment=item.experiment, item_id=item.item_id, model=model, arm=arm,
                system_sha256=prompt_sha, response=resp.text, truncated=resp.truncated,
                latency_s=resp.latency_s or round(time.monotonic() - started, 3),
                served_model=resp.served_model, seed=seed, max_tokens=cap,
            )
            counts["generated"] += 1
        except Exception as exc:  # noqa: BLE001 - isolatable failures are recorded, fatal ones stop
            if not isolatable(exc):
                raise
            rec = TranscriptRecord(
                experiment=item.experiment, item_id=item.item_id, model=model, arm=arm,
                system_sha256=prompt_sha, response=None, error=f"{type(exc).__name__}: {exc}"[:300],
                seed=seed, max_tokens=cap,
            )
            counts["errored"] += 1
        store.append(rec)
        done_cache[key][(item.item_id, arm)] = rec
        if on_progress:
            on_progress(
                f"{model} {item.experiment} {item.item_id} {arm}: "
                f"{'ERROR ' + rec.error if rec.error else f'{rec.latency_s}s'}"
            )
    return counts
