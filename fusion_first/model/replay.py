"""Deterministic model replay: cassettes map request hash -> recorded response.

The request key does not include which judge answered, so the recorded `model` field is the
provenance record; `ReplayModelClient(expected_models=...)` refuses entries from any other model.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import tempfile
import time
from dataclasses import dataclass

from fusion_first.errors import FatalRunError
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse

DEMO_MODELS = frozenset({"demo-heuristic-judge", "bootstrap"})


class CassetteMiss(FatalRunError, KeyError):
    """No recorded response under strict replay."""


class ProvenanceMismatch(FatalRunError):
    """A cassette entry was recorded by a model other than the one this replay expects."""


class Cassette:
    def __init__(self, entries: dict[str, dict] | None = None):
        self.entries: dict[str, dict] = entries or {}

    @classmethod
    def load(cls, path: str | pathlib.Path) -> Cassette:
        p = pathlib.Path(path)
        if not p.exists():
            return cls({})
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def save(self, path: str | pathlib.Path) -> None:
        """Atomic write (temp file + os.replace)."""
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(self.entries, indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(blob)
            for attempt in range(12):  # Windows: a reader / AV / OneDrive may hold the file briefly
                try:
                    os.replace(tmp, p)
                    break
                except PermissionError:
                    if attempt == 11:
                        raise
                    time.sleep(0.025 * (1 + attempt % 4))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def put(self, key: str, response: ModelResponse) -> None:
        self.entries[key] = response.model_dump()

    def get(self, key: str) -> ModelResponse | None:
        raw = self.entries.get(key)
        return ModelResponse(**raw) if raw is not None else None

    def models(self) -> set[str]:
        return {str(e.get("model", "")) for e in self.entries.values()}

    def __len__(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class Provenance:
    models: frozenset[str]
    demonstration: bool  # any entry from a stand-in (non-real) judge
    mixed: bool  # entries from more than one model: never trustworthy


def cassette_provenance(cassette: Cassette) -> Provenance:
    models = frozenset(cassette.models())
    return Provenance(
        models=models,
        demonstration=bool(models & DEMO_MODELS) or not models,
        mixed=len(models) > 1,
    )


class ReplayModelClient:
    """Serves recorded responses. Strict: a miss is an error (a stale gold set can't silently pass);
    non-strict returns `bootstrap_response`. `expected_models` refuses entries from other models."""

    def __init__(
        self,
        cassette: Cassette,
        strict: bool = True,
        bootstrap_response: ModelResponse | None = None,
        expected_models: set[str] | frozenset[str] | None = None,
    ):
        self.cassette = cassette
        self.strict = strict
        self.bootstrap_response = bootstrap_response
        self.expected_models = frozenset(expected_models) if expected_models else None
        self.misses: list[str] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        key = request.cache_key()
        found = self.cassette.get(key)
        if found is not None:
            if self.expected_models is not None and found.model not in self.expected_models:
                raise ProvenanceMismatch(
                    f"entry {key[:12]}… was recorded by '{found.model}', expected one of "
                    f"{sorted(self.expected_models)}"
                )
            return found
        self.misses.append(key)
        if self.strict:
            raise CassetteMiss(
                f"no recorded response for request {key[:12]}… "
                f"(role={request.role.value}); record a cassette or run with strict=False"
            )
        if self.bootstrap_response is not None:
            return self.bootstrap_response
        return ModelResponse(text="", model="bootstrap", stop_reason="bootstrap")


class RecordModelClient:
    """Wraps a live ModelClient and records every response into a cassette."""

    def __init__(self, inner: ModelClient, cassette: Cassette):
        self.inner = inner
        self.cassette = cassette

    async def complete(self, request: ModelRequest) -> ModelResponse:
        key = request.cache_key()
        cached = self.cassette.get(key)
        if cached is not None:
            return cached
        response = await self.inner.complete(request)
        self.cassette.put(key, response)
        return response


class CheckpointingRecordClient:
    """A recorder that never calls the model twice for a key (even concurrently) and saves every
    `every` new entries, so an interruption loses at most `every - 1`. Call `flush()` at the end."""

    def __init__(
        self, inner: ModelClient, cassette: Cassette, path: str | pathlib.Path | None, every: int = 10
    ):
        self.inner = inner
        self.cassette = cassette
        self.path = pathlib.Path(path) if path is not None else None
        self.every = max(1, every)
        self.new_entries = 0
        self._unsaved = 0
        self._locks: dict[str, asyncio.Lock] = {}

    async def complete(self, request: ModelRequest) -> ModelResponse:
        key = request.cache_key()
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.cassette.get(key)
            if cached is not None:
                return cached
            response = await self.inner.complete(request)
            self.cassette.put(key, response)
            self.new_entries += 1
            self._unsaved += 1
            if self._unsaved >= self.every:
                self.flush()
            return response

    def flush(self) -> None:
        if self.path is not None and (self._unsaved or not self.path.exists()):
            self.cassette.save(self.path)
        self._unsaved = 0
