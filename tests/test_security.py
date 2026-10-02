from __future__ import annotations

import pytest

from fusion_first.model.client import ModelRequest, ModelResponse, ModelRole
from fusion_first.security.budget import (
    BudgetedModelClient,
    BudgetExceeded,
    BudgetLimits,
    ModelNotAllowed,
)
from fusion_first.security.redaction import contains_secret, redact, redact_mapping

# ------------------------------- redaction -------------------------------


@pytest.mark.unit
def test_redact_masks_api_keys_and_tokens():
    txt = "here is the key sk-abcdef123456 and Bearer abcdefghijklmnop"
    out = redact(txt)
    assert "sk-abcdef123456" not in out
    assert "abcdefghijklmnop" not in out
    assert "[REDACTED]" in out


@pytest.mark.unit
def test_redact_masks_assignment_form():
    assert "hunter2" not in redact("password = hunter2")
    assert "topsecret" not in redact("API_KEY: topsecret")


@pytest.mark.unit
def test_redact_mapping_by_key_name_and_value():
    data = {"authorization": "Bearer xyztoken12345", "note": "email me at a@b.com", "n": 3}
    red = redact_mapping(data)
    assert red["authorization"] == "[REDACTED]"
    assert "a@b.com" not in red["note"]
    assert red["n"] == 3


@pytest.mark.unit
def test_contains_secret_ignores_plain_email():
    assert contains_secret("sk-abcdef123456") is True
    assert contains_secret("just email me at a@b.com") is False


@pytest.mark.unit
def test_linear_time_patterns_match_the_original_definitions():
    """The linear-time strict-assignment and JWT patterns agree with the quadratic reference regexes:
    same truth value for the checks, same spans for redact()."""
    import random
    import re

    from fusion_first.security import redaction as r

    old_strict = re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*[^\s\"']*[0-9_\-][^\s\"']*")
    old_jwt = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
    jwt_sub, jwt_search = dict(r._PATTERNS)["jwt"], r._SEARCH_ONLY["jwt"]
    frags = ["token", "api_key", "api-key", "apikey", "secret", "pwd", "passwd", "password", "=", ":", " ", "'",
             '"', "1", "_", "-", "a", "Z", "eyJ", "ey", "J", ".", "..", "@", "TOKEN", "Api_Key"]
    rng = random.Random(20260926)
    for _ in range(30_000):
        s = "".join(rng.choice(frags) for _ in range(rng.randint(1, 16)))
        assert bool(old_strict.search(s)) == bool(r._STRICT_ASSIGN.search(s)), s
        assert bool(old_jwt.search(s)) == bool(jwt_search.search(s)), s
        assert [m.span() for m in old_jwt.finditer(s)] == [m.span() for m in jwt_sub.finditer(s)], s


@pytest.mark.unit
def test_secret_checks_are_fast_on_pathological_text():
    import time

    from fusion_first.security.redaction import contains_secret_strict

    t = time.perf_counter()
    for text in ("eyJ" * 7000, "token=" * 4000, "api_key=" * 3000, "eyJa." * 5000):
        contains_secret_strict(text)
        contains_secret(text)
    assert time.perf_counter() - t < 0.5
    assert contains_secret_strict("token=abc123") and contains_secret_strict("x eyJa.b.c y")
    assert not contains_secret_strict("password: click the link")


# ------------------------------- budget / circuit breaker -------------------------------


class _Counter:
    def __init__(self, out_tokens: int = 10):
        self.out_tokens = out_tokens
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        return ModelResponse(text="ok", model=request.model_id or "m", output_tokens=self.out_tokens)


@pytest.mark.unit
async def test_budget_caps_call_count():
    client = BudgetedModelClient(_Counter(), limits=BudgetLimits(max_calls=2))
    req = ModelRequest(role=ModelRole.JUDGE)
    await client.complete(req)
    await client.complete(req)
    with pytest.raises(BudgetExceeded):
        await client.complete(req)  # 3rd call blocked


@pytest.mark.unit
async def test_budget_caps_output_tokens():
    client = BudgetedModelClient(_Counter(out_tokens=150), limits=BudgetLimits(max_output_tokens=100))
    with pytest.raises(BudgetExceeded):
        await client.complete(ModelRequest(role=ModelRole.JUDGE))


class _CapturingClient:
    def __init__(self):
        self.seen_max_tokens: int | None = None

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.seen_max_tokens = request.max_tokens
        return ModelResponse(text="ok", model="m", output_tokens=1)


@pytest.mark.unit
async def test_budget_clamps_per_call_output_cap():
    inner = _CapturingClient()
    client = BudgetedModelClient(inner, limits=BudgetLimits(per_call_output_cap=256))
    await client.complete(ModelRequest(role=ModelRole.JUDGE, max_tokens=9999))
    assert inner.seen_max_tokens == 256  # clamped down from 9999


@pytest.mark.unit
async def test_budget_enforces_model_allowlist():
    client = BudgetedModelClient(_Counter())
    with pytest.raises(ModelNotAllowed):
        await client.complete(ModelRequest(role=ModelRole.TARGET, model_id="evil-model-9000"))
    await client.complete(ModelRequest(role=ModelRole.JUDGE, model_id="claude-sonnet-5"))
