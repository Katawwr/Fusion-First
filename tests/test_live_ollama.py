"""Opt-in live smoke for the local Ollama backend (free, no key). Run: pytest -m live tests/test_live_ollama.py"""

from __future__ import annotations

import pytest

from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.providers.ollama import OllamaModelClient, ollama_available, ollama_models

MODEL = "qwen2.5:1.5b"

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def _need_ollama():
    if not ollama_available() or not any(m["name"] == MODEL for m in ollama_models()):
        pytest.skip(f"Ollama with {MODEL} not available")


async def test_live_generation_and_logprobs():
    c = OllamaModelClient(model=MODEL, num_ctx=2048)
    req = ModelRequest(
        role=ModelRole.TARGET, model_id=MODEL, max_tokens=1, logprobs=5, seed=1,
        messages=[{"role": "user", "content": "Is the sky green? Answer yes or no."}],
    )
    resp = await c.complete(req)
    assert resp.text.strip()
    assert resp.top_logprobs and resp.top_logprobs[0]["top"]
    assert resp.truncated is True  # we asked for exactly one token
    assert resp.served_model.startswith("qwen2.5")


async def test_live_seeded_generation_is_repeatable():
    c = OllamaModelClient(model=MODEL, num_ctx=2048)
    req = ModelRequest(
        role=ModelRole.TARGET, model_id=MODEL, max_tokens=24, seed=11, temperature=0.0,
        messages=[{"role": "user", "content": "Name three primary colours."}],
    )
    a, b = await c.complete(req), await c.complete(req)
    assert a.text == b.text
