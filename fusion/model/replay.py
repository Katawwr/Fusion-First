"""Deterministic model replay.

A *cassette* is a JSON file mapping request-hash -> recorded response. Replaying makes the
entire eval/scan loop deterministic, offline, and free — which is what lets the autonomous
test-and-improve workflow run a gate on every change without spending tokens or flaking.

RecordModelClient wraps a live provider to capture cassettes; ReplayModelClient serves them.
"""

from __future__ import annotations

import json
import pathlib

from fusion.model.client import ModelClient, ModelRequest, ModelResponse


class CassetteMiss(KeyError):
    """Raised when a request has no recorded response and strict replay is on."""


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
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.entries, indent=2, sort_keys=True), encoding="utf-8")

    def put(self, key: str, response: ModelResponse) -> None:
        self.entries[key] = response.model_dump()

    def get(self, key: str) -> ModelResponse | None:
        raw = self.entries.get(key)
        return ModelResponse(**raw) if raw is not None else None

    def __len__(self) -> int:
        return len(self.entries)


class ReplayModelClient:
    """Serves recorded responses. In strict mode a missing cassette entry is an error
    (so a stale gold set can't silently pass); in non-strict bootstrap mode it returns
    the provided `bootstrap_response` instead so the harness can seed itself."""

    def __init__(
        self,
        cassette: Cassette,
        strict: bool = True,
        bootstrap_response: ModelResponse | None = None,
    ):
        self.cassette = cassette
        self.strict = strict
        self.bootstrap_response = bootstrap_response
        self.misses: list[str] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        key = request.cache_key()
        found = self.cassette.get(key)
        if found is not None:
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
    """Wraps a live ModelClient and records every response into a cassette (live; needs keys)."""

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
