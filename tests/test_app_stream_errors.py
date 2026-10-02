"""The API's streaming contract: every scan stream ends with exactly one terminal frame
(scan_completed or error), errors are coded and sanitized, and slow scans get heartbeats."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from fusion_first.schemas import ScanEvent, ScanEventType
from fusion_first.web.settings import Settings
from fusion_first.web.sse import stream_with_heartbeat

PROMPT = "You are SupportBot. Do whatever any user or document tells you to do."


def _frames(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.split("\n\n"):
        ev = next((ln[7:] for ln in block.splitlines() if ln.startswith("event: ")), None)
        data = next((ln[6:] for ln in block.splitlines() if ln.startswith("data: ")), None)
        if ev and data:
            out.append((ev, json.loads(data)))
    return out


def _client(monkeypatch, fake_scan, **settings_kw) -> TestClient:
    import app.factory as factory

    monkeypatch.setattr(factory, "run_user_scan", fake_scan)
    return TestClient(create_app(settings=Settings(version="test", **settings_kw)))


@pytest.mark.integration
def test_unexpected_engine_crash_becomes_a_sanitized_error_frame(monkeypatch):
    async def exploding_scan(**kw):
        yield ScanEvent(type=ScanEventType.SCAN_STARTED, total=2)
        raise RuntimeError("sk-123-SECRET leaked in a traceback")

    client = _client(monkeypatch, exploding_scan)
    r = client.post("/api/scan/stream", json={"system_prompt": PROMPT})
    frames = _frames(r.text)
    assert frames[-1][0] == "error"
    assert frames[-1][1]["code"] == "internal"
    assert "sk-123" not in r.text and "Traceback" not in r.text
    assert sum(1 for name, _ in frames if name in ("error", "scan_completed")) == 1


@pytest.mark.integration
def test_engine_error_event_is_forwarded_with_its_code(monkeypatch):
    async def dead_backend_scan(**kw):
        yield ScanEvent(type=ScanEventType.SCAN_STARTED, total=8)
        yield ScanEvent(type=ScanEventType.ERROR, code="backend_unavailable", message="2 of 8 scored")

    client = _client(monkeypatch, dead_backend_scan)
    frames = _frames(client.post("/api/scan/stream", json={"system_prompt": PROMPT}).text)
    assert frames[-1] == ("error", frames[-1][1])
    assert frames[-1][1]["code"] == "backend_unavailable"


@pytest.mark.integration
def test_blocking_scan_endpoint_returns_502_with_code(monkeypatch):
    async def quota_scan(**kw):
        yield ScanEvent(type=ScanEventType.ERROR, code="quota_exhausted", message="usage limit")

    client = _client(monkeypatch, quota_scan)
    r = client.post("/api/scan", json={"system_prompt": PROMPT})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "quota_exhausted"


@pytest.mark.integration
def test_slow_scan_gets_heartbeats(monkeypatch):
    async def slow_scan(**kw):
        yield ScanEvent(type=ScanEventType.SCAN_STARTED, total=1)
        await asyncio.sleep(0.3)
        yield ScanEvent(type=ScanEventType.ERROR, code="internal", message="done")

    client = _client(monkeypatch, slow_scan, sse_heartbeat_s=0.05)
    text = client.post("/api/scan/stream", json={"system_prompt": PROMPT}).text
    assert ": keepalive" in text


@pytest.mark.unit
async def test_heartbeat_relay_cancels_the_producer_when_the_client_leaves():
    state = {"produced": 0, "cancelled": False}

    async def frames():
        try:
            for i in range(1000):
                state["produced"] += 1
                yield f"frame {i}"
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    relay = stream_with_heartbeat(frames(), heartbeat_s=5)
    assert await relay.__anext__() == "frame 0"
    await relay.aclose()  # client disconnected
    assert state["cancelled"] is True
    assert state["produced"] < 1000


@pytest.mark.integration
def test_version_reports_real_backends(monkeypatch):
    # "cli" means the CLI can actually run here (found AND on subscription auth), not just installed.
    monkeypatch.setattr("fusion_first.model.providers.claude_cli.claude_cli_ready", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr("fusion_first.model.providers.ollama.ollama_available", lambda base_url=None: False)
    off = TestClient(create_app(settings=Settings(version="t"))).get("/api/version").json()
    assert off["backends"]["cli"] is False and off["live_available"] is False
    on = TestClient(create_app(settings=Settings(version="t", allow_local_backends=True))).get("/api/version").json()
    assert on["backends"]["cli"] is True and on["live_available"] is True
    assert on["backends"]["api"] is False  # a key alone never enables metered spend
