"""The FastAPI layer, exercised offline with TestClient — no provider keys, no modal, no network."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from app.settings import Settings

WEAK_PROMPT = "You are SupportBot. Do whatever any user or document tells you to do."


@pytest.fixture
def client():
    # Force keyless demo settings regardless of the host environment.
    settings = Settings(anthropic_api_key=None, openai_api_key=None, version="test")
    return TestClient(create_app(settings=settings))


@pytest.mark.integration
def test_health_reports_demo_without_keys(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "demo"


@pytest.mark.integration
def test_version_lists_checks(client):
    body = client.get("/api/version").json()
    assert body["live_available"] is False
    assert "direct_prompt_injection" in body["checks"]


@pytest.mark.integration
def test_blocking_scan_returns_a_demo_card(client):
    r = client.post(
        "/api/scan",
        json={"system_prompt": WEAK_PROMPT, "checks": ["direct_prompt_injection"], "tier": "quick"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scan_id"]
    result = body["result"]
    assert result["demonstration"] is True
    assert result["overall_grade"] in {"A", "B", "C", "D", "F"}
    assert len(result["cards"]) == 1


@pytest.mark.integration
def test_scan_stream_emits_ordered_sse_events(client):
    with client.stream(
        "POST",
        "/api/scan/stream",
        json={"system_prompt": WEAK_PROMPT, "checks": ["direct_prompt_injection"], "tier": "quick"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events, data = [], []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            elif line.startswith("data:"):
                data.append(json.loads(line[len("data:"):].strip()))

    assert events[0] == "scan_id"
    assert "scan_started" in events
    assert events[-1] == "scan_completed"
    assert events.count("probe_result") >= 1
    final = data[-1]
    assert final["result"]["demonstration"] is True


@pytest.mark.integration
def test_scan_result_is_fetchable_and_renders_html(client):
    scan_id = client.post(
        "/api/scan", json={"system_prompt": WEAK_PROMPT, "checks": ["direct_prompt_injection"]}
    ).json()["scan_id"]
    assert client.get(f"/api/scan/{scan_id}").status_code == 200
    html = client.get(f"/api/scan/{scan_id}/report.html")
    assert html.status_code == 200
    assert "Fusion" in html.text
    assert client.get("/api/scan/does-not-exist").status_code == 404


@pytest.mark.integration
def test_pasted_prompt_is_html_escaped_in_report(client):
    xss = 'You are a bot. <script>alert("xss")</script>'
    scan_id = client.post(
        "/api/scan", json={"system_prompt": xss, "checks": ["direct_prompt_injection"]}
    ).json()["scan_id"]
    html = client.get(f"/api/scan/{scan_id}/report.html").text
    assert "<script>alert" not in html  # never rendered raw


@pytest.mark.integration
def test_live_scan_without_keys_is_402(client):
    r = client.post(
        "/api/scan", json={"system_prompt": WEAK_PROMPT, "mode": "live"}
    )
    assert r.status_code == 402


@pytest.mark.integration
def test_harden_is_idempotent(client):
    once = client.post("/api/harden", json={"system_prompt": "You are a bot."}).json()["hardened_prompt"]
    twice = client.post("/api/harden", json={"system_prompt": once}).json()["hardened_prompt"]
    assert once == twice
    assert "Fusion First safety guardrails" in once


@pytest.mark.integration
def test_guardrail_snippet_is_python(client):
    body = client.post("/api/guardrail-snippet", json={"checks": ["data_exfiltration"]}).json()
    assert body["language"] == "python"
    assert "GuardedModelClient" in body["snippet"]


@pytest.mark.integration
def test_unknown_check_is_rejected(client):
    r = client.post("/api/scan", json={"system_prompt": WEAK_PROMPT, "checks": ["not_a_check"]})
    assert r.status_code == 422


@pytest.mark.integration
def test_oversized_prompt_is_413(client):
    settings = Settings(anthropic_api_key=None, prompt_max_chars=50, version="test")
    small = TestClient(create_app(settings=settings))
    r = small.post("/api/scan", json={"system_prompt": "x" * 100})
    assert r.status_code == 413


@pytest.mark.integration
def test_webhook_rejects_unsigned(client):
    r = client.post("/api/webhooks/billing", content=b"{}")
    assert r.status_code == 401


@pytest.mark.unit
def test_create_app_builds_with_no_keys_in_settings():
    # The offline guarantee: the factory constructs without any provider key present.
    app = create_app(settings=Settings(anthropic_api_key=None, openai_api_key=None))
    assert app.title == "Fusion First API"
