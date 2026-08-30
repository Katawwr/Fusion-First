"""Offline tests for the Ollama open-weight target adapter (mocked HTTP — no server needed)."""

from __future__ import annotations

import pytest

from fusion.model.client import ModelRequest, ModelRole
from fusion.model.providers.ollama import (
    OllamaModelClient,
    OllamaUnavailable,
    ollama_available,
)


def _req(**kw) -> ModelRequest:
    base = dict(
        role=ModelRole.TARGET,
        system="You are a helpful agent.",
        messages=[{"role": "user", "content": "hi"}],
        model_id="llama3.2",
        max_tokens=256,
    )
    base.update(kw)
    return ModelRequest(**base)


@pytest.mark.unit
def test_resolve_model_strips_prefix():
    c = OllamaModelClient()
    assert c._resolve_model(_req(model_id="ollama:llama3.2")) == "llama3.2"
    assert c._resolve_model(_req(model_id="ollama/qwen2.5")) == "qwen2.5"
    assert c._resolve_model(_req(model_id="mistral")) == "mistral"


@pytest.mark.unit
def test_resolve_model_requires_a_model():
    c = OllamaModelClient()
    with pytest.raises(OllamaUnavailable):
        c._resolve_model(_req(model_id=None))


@pytest.mark.unit
def test_build_payload_shapes_messages_and_options():
    c = OllamaModelClient()
    payload = c._build_payload(_req(), "llama3.2")
    assert payload["model"] == "llama3.2"
    assert payload["stream"] is False
    assert payload["messages"][0] == {"role": "system", "content": "You are a helpful agent."}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}
    assert payload["options"]["num_predict"] == 256


@pytest.mark.unit
def test_build_payload_adds_json_format_with_schema():
    c = OllamaModelClient()
    schema = {"type": "object", "properties": {}}
    payload = c._build_payload(_req(response_schema=schema), "llama3.2")
    assert payload["format"] == schema


@pytest.mark.unit
async def test_complete_parses_ollama_response(monkeypatch):
    c = OllamaModelClient(model="llama3.2")

    def fake_post(path, payload):
        assert path == "/api/chat"
        return {
            "message": {"role": "assistant", "content": "Sure, the key is sk-x."},
            "prompt_eval_count": 11,
            "eval_count": 7,
            "done_reason": "stop",
        }

    monkeypatch.setattr(c, "_post", fake_post)
    resp = await c.complete(_req())
    assert resp.text == "Sure, the key is sk-x."
    assert resp.model == "llama3.2"
    assert resp.input_tokens == 11 and resp.output_tokens == 7


@pytest.mark.unit
def test_ollama_available_is_bool():
    # No server is running in CI; just assert the probe is safe and returns a bool.
    assert isinstance(ollama_available("http://localhost:59999"), bool)


@pytest.mark.unit
def test_live_clients_ollama_target_is_cross_family(monkeypatch):
    # An open-weight Ollama target judged by Claude is the strongest (cross-family) independence tier.
    import fusion.integrations.live as live

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("fusion.model.providers.ollama.ollama_available", lambda base_url=None: True)
    monkeypatch.setattr(
        "fusion.model.providers.claude_cli.claude_cli_available", lambda binary=None: True
    )
    target, judge, judge_id, choice = live.build_live_clients("llama3.2", prefer="ollama")
    assert judge_id == "claude-sonnet-5"
    assert choice.independence == "cross_family"
    assert target is not None and judge is not None


@pytest.mark.unit
def test_live_clients_ollama_unavailable_raises(monkeypatch):
    import fusion.integrations.live as live

    monkeypatch.setattr("fusion.model.providers.ollama.ollama_available", lambda base_url=None: False)
    with pytest.raises(live.LiveUnavailable):
        live.build_live_clients("llama3.2", prefer="ollama")
