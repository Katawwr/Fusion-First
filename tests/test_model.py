from __future__ import annotations

import pytest

from fusion_first.model.client import ModelRequest, ModelResponse, ModelRole
from fusion_first.model.registry import ModelRegistry
from fusion_first.model.replay import Cassette, CassetteMiss, RecordModelClient, ReplayModelClient


@pytest.mark.unit
def test_registry_resolves_roles_and_families():
    reg = ModelRegistry()
    assert reg.resolve("judge_primary") == "claude-sonnet-5"
    assert reg.family_of("claude-sonnet-5") == "anthropic"
    assert reg.family_of("gpt-4o") == "openai"


@pytest.mark.unit
def test_registry_rejects_unknown_model():
    reg = ModelRegistry()
    with pytest.raises(ValueError):
        reg.require_allowed("totally-made-up-model")


@pytest.mark.unit
def test_self_family_guard_picks_cross_family_for_claude_target():
    reg = ModelRegistry()
    choice = reg.choose_judge_with_disclosure("claude-opus-4-8")
    assert (choice.judge_id, choice.independence) == ("gpt-4o", "cross_family")


@pytest.mark.unit
def test_cache_key_is_stable_and_sensitive():
    a = ModelRequest(role=ModelRole.JUDGE, system="s", messages=[{"role": "user", "content": "x"}])
    b = ModelRequest(role=ModelRole.JUDGE, system="s", messages=[{"role": "user", "content": "x"}])
    c = ModelRequest(role=ModelRole.JUDGE, system="s", messages=[{"role": "user", "content": "y"}])
    assert a.cache_key() == b.cache_key()
    assert a.cache_key() != c.cache_key()


@pytest.mark.unit
def test_cassette_roundtrip(tmp_path):
    cas = Cassette()
    req = ModelRequest(role=ModelRole.JUDGE, system="hi")
    cas.put(req.cache_key(), ModelResponse(text="ok", model="m", output_tokens=3))
    path = tmp_path / "c.json"
    cas.save(path)
    loaded = Cassette.load(path)
    got = loaded.get(req.cache_key())
    assert got is not None and got.text == "ok" and got.output_tokens == 3


@pytest.mark.unit
async def test_replay_strict_miss_raises():
    client = ReplayModelClient(Cassette(), strict=True)
    with pytest.raises(CassetteMiss):
        await client.complete(ModelRequest(role=ModelRole.JUDGE, system="unseen"))


@pytest.mark.unit
async def test_replay_hit_returns_recorded():
    cas = Cassette()
    req = ModelRequest(role=ModelRole.JUDGE, system="seen")
    cas.put(req.cache_key(), ModelResponse(text="recorded", model="m"))
    client = ReplayModelClient(cas, strict=True)
    out = await client.complete(req)
    assert out.text == "recorded"


@pytest.mark.unit
async def test_replay_bootstrap_mode_returns_default():
    boot = ModelResponse(text="{}", model="bootstrap")
    client = ReplayModelClient(Cassette(), strict=False, bootstrap_response=boot)
    out = await client.complete(ModelRequest(role=ModelRole.JUDGE, system="unseen"))
    assert out.model == "bootstrap"
    assert len(client.misses) == 1


class _FakeLive:
    async def complete(self, request):
        return ModelResponse(text="live-answer", model="fake")


@pytest.mark.unit
async def test_record_client_captures(tmp_path):
    cas = Cassette()
    rec = RecordModelClient(_FakeLive(), cas)
    req = ModelRequest(role=ModelRole.TARGET, system="q")
    out = await rec.complete(req)
    assert out.text == "live-answer"
    assert cas.get(req.cache_key()).text == "live-answer"  # captured for replay


@pytest.mark.unit
def test_pinned_cache_key_is_stable_across_schema_additions():
    """Every committed cassette is keyed by this hash. New optional request fields must not change
    the key of a request that doesn't set them: pin one known key."""
    from fusion_first.model.client import ModelRequest, ModelRole

    req = ModelRequest(role=ModelRole.JUDGE, system="s", messages=[{"role": "user", "content": "x"}])
    assert req.cache_key() == PINNED_KEY


PINNED_KEY = "c3f720dd02ecd69c4a6ed9d46318c79faff26b5cdf5f02e7b9a25f794b1aa6f5"


# ---- native tool calls (ModelRequest.tools / ModelResponse.tool_calls) -----------------------------

# cache_key() of _target_req(), computed on the base commit (2b5cad2) before `tools` existed.
PINNED_TARGET_KEY = "1f571288f3f9e8960a0e64437ecb757cd01cdd8a677c4b9c7a57dd11a3d91eda"

TOOLS = [{"type": "function", "function": {
    "name": "send_email", "description": "Send an email.",
    "parameters": {"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]}}}]


def _target_req(**kw) -> ModelRequest:
    return ModelRequest(role=ModelRole.TARGET, system="s", messages=[{"role": "user", "content": "hi"}],
                        model_id="m", **kw)


@pytest.mark.unit
def test_a_request_without_tools_keeps_its_base_commit_key():
    assert _target_req().cache_key() == PINNED_TARGET_KEY
    assert _target_req(tools=None).cache_key() == PINNED_TARGET_KEY


@pytest.mark.unit
def test_tools_change_the_cache_key():
    with_tools = _target_req(tools=TOOLS).cache_key()
    assert with_tools != PINNED_TARGET_KEY
    assert with_tools == _target_req(tools=TOOLS).cache_key()
    other = [{"type": "function", "function": {**TOOLS[0]["function"], "name": "read_inbox"}}]
    assert _target_req(tools=other).cache_key() != with_tools


@pytest.mark.unit
def test_tool_calls_default_to_none():
    assert ModelResponse(text="x", model="m").tool_calls is None


TOOL_CALLS = [{"name": "send_email", "arguments": {"to": "a@example.com"}},
              {"name": "read_inbox", "arguments": {}, "arguments_raw": "{not json"}]


@pytest.mark.unit
def test_tool_calls_survive_a_cassette_save_and_load(tmp_path):
    req = _target_req(tools=TOOLS)
    resp = ModelResponse(text="", model="qwen2.5:7b", tool_calls=TOOL_CALLS)
    cas = Cassette()
    cas.put(req.cache_key(), resp)
    path = tmp_path / "tools.json"
    cas.save(path)
    got = Cassette.load(path).get(req.cache_key())
    assert got == resp
    assert got.tool_calls == TOOL_CALLS


class _FakeToolCaller:
    def __init__(self):
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        return ModelResponse(text="", model="qwen2.5:7b", tool_calls=TOOL_CALLS)


@pytest.mark.unit
async def test_tool_calls_record_then_strict_replay(tmp_path):
    from fusion_first.model.replay import CheckpointingRecordClient

    path = tmp_path / "rec.json"
    live = _FakeToolCaller()
    rec = CheckpointingRecordClient(live, Cassette(), path, every=1)
    req = _target_req(tools=TOOLS)
    recorded = await rec.complete(req)
    rec.flush()
    replay = ReplayModelClient(Cassette.load(path), strict=True, expected_models={"qwen2.5:7b"})
    assert await replay.complete(req) == recorded
    assert (await replay.complete(req)).tool_calls == TOOL_CALLS
    with pytest.raises(CassetteMiss):  # the same request without tools is a different key
        await replay.complete(_target_req())
    assert live.calls == 1
