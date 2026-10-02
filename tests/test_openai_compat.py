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
