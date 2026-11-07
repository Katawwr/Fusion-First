"""The OpenAI-compatible target (vLLM, LM Studio, llama.cpp, Ollama /v1). HTTP is faked at urlopen."""

from __future__ import annotations

import io
import json

import pytest

from fusion_first.backends.resolve import (
    BackendUnavailable,
    SpecError,
    build_target_client,
    parse_target,
)
from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.providers import openai_compat
from fusion_first.model.providers.openai_compat import (
    OpenAICompatModelClient,
    OpenAICompatUnavailable,
)


class _Resp(io.BytesIO):
    status = 200


def _fake_server(monkeypatch, reply: dict, sent: list):
    def urlopen(req, timeout=None):
        sent.append({"url": req.full_url, "headers": dict(req.header_items()),
                     "payload": json.loads(req.data.decode("utf-8"))})
        return _Resp(json.dumps(reply).encode("utf-8"))

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    monkeypatch.setattr(openai_compat._OPENER, "open", urlopen)


def _req(**kw):
    base = dict(role=ModelRole.TARGET, system="You are SupportBot.", messages=[{"role": "user", "content": "hi"}],
                max_tokens=64, temperature=0.0, seed=7)
    base.update(kw)
    return ModelRequest(**base)


REPLY = {"model": "Qwen/Qwen2.5-7B-Instruct",
         "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 12, "completion_tokens": 3}}


@pytest.mark.unit
async def test_sends_a_chat_completion_and_reads_the_answer(monkeypatch):
    sent = []
    _fake_server(monkeypatch, REPLY, sent)
    client = OpenAICompatModelClient("http://127.0.0.1:8000/v1/", "Qwen/Qwen2.5-7B-Instruct")
    resp = await client.complete(_req())
    assert sent[0]["url"] == "http://127.0.0.1:8000/v1/chat/completions"
    p = sent[0]["payload"]
    assert p["model"] == "Qwen/Qwen2.5-7B-Instruct" and p["max_tokens"] == 64 and p["seed"] == 7
    assert p["messages"] == [{"role": "system", "content": "You are SupportBot."}, {"role": "user", "content": "hi"}]
    assert (resp.text, resp.truncated, resp.served_model) == ("Hello!", False, "Qwen/Qwen2.5-7B-Instruct")
    assert (resp.input_tokens, resp.output_tokens) == (12, 3)


@pytest.mark.unit
async def test_a_length_cut_answer_is_marked_truncated(monkeypatch):
    sent = []
    cut = {**REPLY, "choices": [{"message": {"content": "Hel"}, "finish_reason": "length"}]}
    _fake_server(monkeypatch, cut, sent)
    resp = await OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m").complete(_req())
    assert resp.truncated is True


@pytest.mark.unit
async def test_offline_switch_refuses_without_a_request(monkeypatch):
    sent = []
    _fake_server(monkeypatch, REPLY, sent)
    monkeypatch.setenv("FUSION_OFFLINE", "1")
    with pytest.raises(OpenAICompatUnavailable):
        await OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m").complete(_req())
    assert sent == []


@pytest.mark.unit
async def test_an_unreachable_server_is_a_clear_error(monkeypatch):
    import urllib.error

    def urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    monkeypatch.setattr(openai_compat._OPENER, "open", urlopen)
    with pytest.raises(OpenAICompatUnavailable, match="127.0.0.1:8000"):
        await OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m").complete(_req())


# ------------------------------------------------------------------ native tool calls

TOOLS = [{"type": "function", "function": {
    "name": "send_email", "description": "Send an email.",
    "parameters": {"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]}}}]


@pytest.mark.unit
async def test_tools_are_sent_and_tool_calls_parsed(monkeypatch):
    sent = []
    calls = {**REPLY, "choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "send_email", "arguments": '{"to": "a@x.org"}'}},
            {"id": "c2", "type": "function", "function": {"name": "send_email", "arguments": '{"to": '}},
            {"id": "c3", "type": "function", "function": {"name": "read_inbox", "arguments": {"n": 2}}},
            {"id": "c4", "type": "function", "function": {"arguments": "{}"}}]}}]}
    _fake_server(monkeypatch, calls, sent)
    resp = await OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m").complete(_req(tools=TOOLS))
    assert sent[0]["payload"]["tools"] == TOOLS
    assert resp.text == ""
    assert resp.tool_calls == [{"name": "send_email", "arguments": {"to": "a@x.org"}},
                               {"name": "send_email", "arguments": {}, "arguments_raw": '{"to": '},
                               {"name": "read_inbox", "arguments": {"n": 2}}]


@pytest.mark.unit
async def test_without_tools_nothing_is_sent_or_parsed(monkeypatch):
    sent = []
    _fake_server(monkeypatch, REPLY, sent)
    client = OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m")
    resp = await client.complete(_req())
    assert "tools" not in sent[0]["payload"]
    assert resp.tool_calls is None
    resp = await client.complete(_req(tools=TOOLS))  # tools offered, plain answer: [] = no call this turn
    assert (resp.text, resp.tool_calls) == ("Hello!", [])


@pytest.mark.unit
async def test_tool_loop_messages_are_translated_for_the_wire(monkeypatch):
    """Assistant tool-call arguments go out as JSON strings (OpenAI requires strings); tool messages keep
    their tool_call_id; everything else is sent unchanged and the request itself is not mutated."""
    sent = []
    _fake_server(monkeypatch, REPLY, sent)
    messages = [
        {"role": "user", "content": "Read my inbox."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1_0", "type": "function", "function": {"name": "read_inbox", "arguments": {"n": 2}}},
            {"id": "call_1_1", "type": "function", "function": {"name": "send_email",
                                                                "arguments": {"to": "a@x.org", "body": "é"}}}]},
        {"role": "tool", "tool_call_id": "call_1_0", "name": "read_inbox", "content": "2 emails"},
        {"role": "tool", "tool_call_id": "call_1_1", "name": "send_email", "content": '{"status": "ok"}'},
    ]
    request = _req(messages=messages, tools=TOOLS)
    before = json.dumps(request.messages)
    await OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m").complete(request)
    wire = sent[0]["payload"]["messages"]
    assert wire[0] == {"role": "system", "content": "You are SupportBot."}
    assert wire[1] == messages[0]
    calls = wire[2]["tool_calls"]
    assert [c["function"]["arguments"] for c in calls] == ['{"n": 2}', '{"to": "a@x.org", "body": "é"}']
    assert all(isinstance(c["function"]["arguments"], str) for c in calls)
    assert [json.loads(c["function"]["arguments"]) for c in calls] == [
        m["function"]["arguments"] for m in messages[1]["tool_calls"]]
    assert [(c["id"], c["type"], c["function"]["name"]) for c in calls] == [
        ("call_1_0", "function", "read_inbox"), ("call_1_1", "function", "send_email")]
    assert {k: v for k, v in wire[2].items() if k != "tool_calls"} == {"role": "assistant", "content": ""}
    assert wire[3:] == [{k: m[k] for k in ("role", "tool_call_id", "content")} for m in messages[2:]]
    assert wire[3]["tool_call_id"] == "call_1_0"
    assert json.dumps(request.messages) == before


@pytest.mark.unit
async def test_a_tool_message_on_the_wire_is_exactly_the_openai_shape(monkeypatch):
    """Strict servers (OpenAI, Groq) reject unknown tool-message keys: the canonical `name` and
    `tool_name` stay off the wire (cassette keys come from the canonical messages, so none change)."""
    sent = []
    _fake_server(monkeypatch, REPLY, sent)
    tool_msg = {"role": "tool", "tool_call_id": "call_1_0", "name": "read_inbox", "tool_name": "read_inbox",
                "content": "2 emails"}
    request = _req(messages=[{"role": "user", "content": "Read my inbox."}, tool_msg], tools=TOOLS)
    await OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m").complete(request)
    assert sent[0]["payload"]["messages"][-1] == {"role": "tool", "tool_call_id": "call_1_0", "content": "2 emails"}
    assert request.messages[-1] == tool_msg  # the request itself is not mutated


@pytest.mark.unit
async def test_string_tool_call_arguments_pass_through(monkeypatch):
    sent = []
    _fake_server(monkeypatch, REPLY, sent)
    msg = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "read_inbox", "arguments": '{"n": 1}'}}]}
    await OpenAICompatModelClient("http://127.0.0.1:8000/v1", "m").complete(_req(messages=[msg], tools=TOOLS))
    assert sent[0]["payload"]["messages"][1] == msg


# ------------------------------------------------------------------ spec + zero-spend gate

@pytest.mark.unit
def test_spec_names_the_server_and_the_model():
    spec = parse_target("openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct")
    assert (spec.backend, spec.base_url, spec.model) == (
        "openai_compat", "http://127.0.0.1:8000/v1", "Qwen/Qwen2.5-7B-Instruct")
    assert spec.label == "openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["openai-compat:http://127.0.0.1:8000/v1", "openai-compat:#m",
                                 "openai-compat:ftp://h/v1#m"])
def test_incomplete_specs_are_refused(bad):
    with pytest.raises(SpecError):
        parse_target(bad)


@pytest.mark.unit
@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/v1", "http://localhost:1234/v1", "http://10.0.0.5:8000/v1",
                                 "http://192.168.1.20:8080/v1", "http://gpu-box:8000/v1", "http://llm.lan:8000/v1"])
def test_local_and_private_servers_need_no_opt_in(monkeypatch, url):
    monkeypatch.delenv("FUSION_ALLOW_API_SPEND", raising=False)
    assert build_target_client(parse_target(f"openai-compat:{url}#m")) is not None


@pytest.mark.unit
@pytest.mark.parametrize("url", ["https://api.openai.com/v1", "https://openrouter.ai/api/v1", "http://8.8.8.8/v1"])
def test_a_public_endpoint_may_be_metered_so_it_needs_the_opt_in(monkeypatch, url):
    monkeypatch.delenv("FUSION_ALLOW_API_SPEND", raising=False)
    with pytest.raises(BackendUnavailable, match="FUSION_ALLOW_API_SPEND"):
        build_target_client(parse_target(f"openai-compat:{url}#gpt-x"))
    monkeypatch.setenv("FUSION_ALLOW_API_SPEND", "1")
    assert build_target_client(parse_target(f"openai-compat:{url}#gpt-x")) is not None


@pytest.mark.unit
def test_the_stored_label_round_trips_and_independence_is_disclosed():
    from fusion_first.runs.engine import independence_of

    label = parse_target("openai-compat:http://127.0.0.1:8000/v1/#meta-llama/Llama-3.1-8B-Instruct").label
    assert parse_target(label).label == label  # what a run stores re-parses to the same target
    assert independence_of(label, "ollama-prob:qwen2.5:7b")[0] == "cross_family"
    qwen = parse_target("openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct").label
    assert independence_of(qwen, "ollama-prob:qwen2.5:7b")[0] == "same_family_cross_tier"


@pytest.mark.integration
@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
async def test_a_redirect_is_refused_and_never_followed(monkeypatch, code):
    """A 307 from the (local, allowed) server must not re-send the body or the bearer key anywhere
    else: that would bypass the zero-spend gate and leak FUSION_TARGET_API_KEY."""
    import http.server
    import threading

    seen_by_elsewhere = []

    def _drain(handler):  # read the body before replying, as real servers do (else Windows resets the socket)
        handler.rfile.read(int(handler.headers.get("Content-Length") or 0))

    class Elsewhere(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            _drain(self)
            seen_by_elsewhere.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(REPLY).encode())

        def do_GET(self):  # noqa: N802 (urllib turns a POST into a GET on 301/302/303)
            seen_by_elsewhere.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(REPLY).encode())

        def log_message(self, *a):
            pass

    other = http.server.HTTPServer(("127.0.0.1", 0), Elsewhere)

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            _drain(self)
            self.send_response(code)
            self.send_header("Location", f"http://127.0.0.1:{other.server_port}/v1/chat/completions")
            self.end_headers()

        def log_message(self, *a):
            pass

    local = http.server.HTTPServer(("127.0.0.1", 0), Redirector)
    for srv in (other, local):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.delenv("FUSION_OFFLINE", raising=False)
        monkeypatch.setenv("FUSION_TARGET_API_KEY", "sk-must-not-travel")
        client = OpenAICompatModelClient(f"http://127.0.0.1:{local.server_port}/v1", "m", timeout=10)
        with pytest.raises(OpenAICompatUnavailable, match="redirect"):
            await client.complete(_req())
        assert seen_by_elsewhere == []
    finally:
        for srv in (other, local):
            srv.shutdown()
