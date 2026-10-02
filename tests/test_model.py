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
