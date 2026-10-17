"""Offline tests for the Ollama open-weight target adapter (mocked HTTP: no server needed)."""

from __future__ import annotations

import pytest

from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.providers.ollama import (
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
    monkeypatch.delenv("FUSION_OFFLINE", raising=False)  # _post is faked below; no real call
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
    assert isinstance(ollama_available("http://localhost:59999"), bool)


@pytest.mark.unit
def test_live_clients_ollama_target_is_cross_family(monkeypatch):
    import fusion_first.integrations.live as live

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("fusion_first.model.providers.ollama.ollama_available", lambda base_url=None: True)
    monkeypatch.setattr(
        "fusion_first.model.providers.claude_cli.claude_cli_ready", lambda *a, **k: (True, "ok")
    )
    target, judge, judge_id, choice = live.build_live_clients("llama3.2", prefer="ollama")
    assert judge_id == "claude-sonnet-5"
    assert choice.independence == "cross_family"
    assert target is not None and judge is not None


@pytest.mark.unit
def test_live_clients_ollama_unavailable_raises(monkeypatch):
    import fusion_first.integrations.live as live

    monkeypatch.setattr("fusion_first.model.providers.ollama.ollama_available", lambda base_url=None: False)
    with pytest.raises(live.LiveUnavailable):
        live.build_live_clients("llama3.2", prefer="ollama")


def _r(**kw):
    base = dict(role=ModelRole.TARGET, system="sys", messages=[{"role": "user", "content": "hi"}], model_id="qwen2.5:3b")
    base.update(kw)
    return ModelRequest(**base)


@pytest.mark.unit
def test_payload_pins_context_and_passes_seed_and_logprobs():
    c = OllamaModelClient(num_ctx=4096)
    p = c._build_payload(_r(seed=7, logprobs=5, max_tokens=1), "qwen2.5:3b")
    assert p["options"]["num_ctx"] == 4096
    assert p["options"]["seed"] == 7
    assert p["logprobs"] is True and p["top_logprobs"] == 5


@pytest.mark.unit
def test_payload_omits_seed_and_logprobs_by_default():
    p = OllamaModelClient()._build_payload(_r(), "qwen2.5:3b")
    assert "seed" not in p["options"] and "logprobs" not in p


@pytest.mark.unit
@pytest.mark.parametrize("mid", ["claude-haiku-4-5", "gpt-4o"])
def test_hosted_model_ids_are_rejected(mid):
    with pytest.raises(OllamaUnavailable, match="not an Ollama model"):
        OllamaModelClient()._resolve_model(_r(model_id=mid))


@pytest.mark.unit
async def test_context_overflow_is_refused_not_truncated(monkeypatch):
    from fusion_first.model.providers.ollama import OllamaContextTooLong

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    c = OllamaModelClient(num_ctx=512)
    monkeypatch.setattr(c, "_post", lambda path, payload: pytest.fail("must not send"))
    with pytest.raises(OllamaContextTooLong):
        await c.complete(_r(system="word " * 2000))


@pytest.mark.unit
async def test_truncation_and_logprobs_are_parsed(monkeypatch):
    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    c = OllamaModelClient()

    def fake_post(path, payload):
        return {
            "model": "qwen2.5:1.5b", "message": {"content": "No"}, "done_reason": "length",
            "prompt_eval_count": 39, "eval_count": 1,
            "logprobs": [{"token": "No", "logprob": -0.05, "bytes": [78, 111],
                          "top_logprobs": [{"token": "No", "logprob": -0.05}, {"token": "Yes", "logprob": -3.1}]}],
        }

    monkeypatch.setattr(c, "_post", fake_post)
    resp = await c.complete(_r(model_id="qwen2.5:1.5b", logprobs=5, max_tokens=1))
    assert resp.truncated is True
    assert resp.served_model == "qwen2.5:1.5b"
    assert resp.top_logprobs[0]["top"][1] == {"token": "Yes", "logprob": -3.1}


@pytest.mark.unit
def test_seed_and_logprobs_change_the_cache_key_only_when_set():
    base = _r()
    assert base.cache_key() == _r(seed=None, logprobs=None).cache_key()
    assert base.cache_key() != _r(seed=1).cache_key()
    assert base.cache_key() != _r(logprobs=5).cache_key()


# ---- native tool calls -------------------------------------------------------------------------

TOOLS = [{"type": "function", "function": {
    "name": "send_email", "description": "Send an email.",
    "parameters": {"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]}}}]


@pytest.mark.unit
def test_payload_carries_tools_when_set():
    p = OllamaModelClient()._build_payload(_r(tools=TOOLS), "qwen2.5:3b")
    assert p["tools"] == TOOLS


@pytest.mark.unit
def test_payload_without_tools_is_unchanged():
    c = OllamaModelClient()
    p = c._build_payload(_r(), "qwen2.5:3b")
    assert "tools" not in p
    assert p == c._build_payload(_r(tools=None), "qwen2.5:3b")


@pytest.mark.unit
def test_tool_schemas_count_toward_the_context_check():
    c = OllamaModelClient()
    assert c._estimate_tokens(_r(tools=None)) == c._estimate_tokens(_r())
    assert c._estimate_tokens(_r(tools=TOOLS)) > c._estimate_tokens(_r())


async def _complete_with(monkeypatch, message: dict, **kw):
    monkeypatch.delenv("FUSION_OFFLINE", raising=False)  # _post is faked below; no real call
    c = OllamaModelClient()
    sent = []

    def fake_post(path, payload):
        sent.append(payload)
        return {"model": "qwen2.5:3b", "message": message, "done_reason": "stop",
                "prompt_eval_count": 20, "eval_count": 5}

    monkeypatch.setattr(c, "_post", fake_post)
    return await c.complete(_r(**kw)), sent


@pytest.mark.unit
async def test_tool_calls_with_dict_arguments_are_parsed(monkeypatch):
    msg = {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "send_email", "arguments": {"to": "a@example.com"}}},
        {"function": {"name": "read_inbox", "arguments": {}}}]}
    resp, sent = await _complete_with(monkeypatch, msg, tools=TOOLS)
    assert sent[0]["tools"] == TOOLS
    assert resp.tool_calls == [{"name": "send_email", "arguments": {"to": "a@example.com"}},
                               {"name": "read_inbox", "arguments": {}}]
    assert resp.text == ""


@pytest.mark.unit
async def test_string_arguments_are_decoded(monkeypatch):
    msg = {"content": "", "tool_calls": [{"function": {"name": "send_email", "arguments": '{"to": "b@x.org"}'}}]}
    resp, _ = await _complete_with(monkeypatch, msg, tools=TOOLS)
    assert resp.tool_calls == [{"name": "send_email", "arguments": {"to": "b@x.org"}}]


@pytest.mark.unit
async def test_broken_string_arguments_keep_the_raw_text(monkeypatch):
    msg = {"content": "", "tool_calls": [{"function": {"name": "send_email", "arguments": '{"to": "b@'}}]}
    resp, _ = await _complete_with(monkeypatch, msg, tools=TOOLS)
    assert resp.tool_calls == [{"name": "send_email", "arguments": {}, "arguments_raw": '{"to": "b@'}]


@pytest.mark.unit
async def test_non_dict_arguments_become_empty_and_nameless_calls_are_skipped(monkeypatch):
    msg = {"content": "", "tool_calls": [
        {"function": {"name": "send_email", "arguments": ["b@x.org"]}},
        {"function": {"name": "send_email", "arguments": '"just a string"'}},
        {"function": {"arguments": {"to": "c@x.org"}}},
        {"function": {"name": "", "arguments": {}}},
        "not a call",
        {"function": {"name": "read_inbox"}}]}
    resp, _ = await _complete_with(monkeypatch, msg, tools=TOOLS)
    assert resp.tool_calls == [{"name": "send_email", "arguments": {}},
                               {"name": "send_email", "arguments": {}},
                               {"name": "read_inbox", "arguments": {}}]


@pytest.mark.unit
async def test_a_plain_answer_has_no_tool_calls(monkeypatch):
    resp, _ = await _complete_with(monkeypatch, {"content": "Done."}, tools=TOOLS)
    assert (resp.text, resp.tool_calls) == ("Done.", None)
    resp, _ = await _complete_with(monkeypatch, {"content": "Done.", "tool_calls": []}, tools=TOOLS)
    assert resp.tool_calls is None


@pytest.mark.unit
async def test_without_tools_the_response_is_unchanged(monkeypatch):
    resp, sent = await _complete_with(monkeypatch, {"content": "hello"})
    assert "tools" not in sent[0]
    assert resp.tool_calls is None
    assert resp.model_dump(exclude={"latency_s", "tool_calls"}) == {
        "text": "hello", "model": "qwen2.5:3b", "input_tokens": 20, "output_tokens": 5, "stop_reason": "stop",
        "served_model": "qwen2.5:3b", "truncated": False, "top_logprobs": None}


@pytest.mark.unit
def test_default_address_is_the_ipv4_loopback(monkeypatch):
    """`localhost` resolves to ::1 first on Windows and Ollama listens on IPv4 (a ~2 s fallback per
    request), so the probes and the client dial 127.0.0.1."""
    import io
    import urllib.parse

    from fusion_first.model.providers import ollama

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    hosts = []

    class _Resp(io.BytesIO):  # what urlopen returns: a readable context manager with a status
        status = 200

    def fake_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        hosts.append(urllib.parse.urlsplit(url).hostname)
        return _Resp(b'{"models": []}')

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)
    ollama.ollama_available()
    ollama.ollama_models()
    assert hosts and set(hosts) == {"127.0.0.1"}
    assert urllib.parse.urlsplit(OllamaModelClient()._base_url).hostname == "127.0.0.1"


@pytest.mark.unit
@pytest.mark.parametrize("prefer", ["ollama", "cli", "auto"])
def test_a_logged_out_cli_fails_before_anything_runs(monkeypatch, prefer):
    """Installed but not logged in: refuse up front, not after the target has already answered."""
    import fusion_first.integrations.live as live

    monkeypatch.setattr("fusion_first.model.providers.ollama.ollama_available", lambda base_url=None: True)
    monkeypatch.setattr("fusion_first.model.providers.claude_cli.claude_cli_available", lambda binary=None: True)
    monkeypatch.setattr("fusion_first.model.providers.claude_cli.claude_cli_ready",
                        lambda *a, **k: (False, "the `claude` CLI is not logged in"))
    with pytest.raises(live.LiveUnavailable, match="not logged in"):
        live.build_live_clients("llama3.2:1b", prefer=prefer)
