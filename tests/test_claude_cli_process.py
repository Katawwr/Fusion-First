"""The claude CLI client's process handling, with a fake subprocess: prompt over stdin (never argv),
over-long command lines refused, throttling retried with backoff, a USAGE LIMIT never retried into
overage, timeouts kill the process, spawn errors are clean."""

from __future__ import annotations

import json

import pytest

from fusion_first.errors import ProviderTimeout
from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.providers import claude_cli
from fusion_first.model.providers.claude_cli import (
    ClaudeCliModelClient,
    ClaudeCliPromptTooLong,
    ClaudeCliQuotaExhausted,
    ClaudeCliRateLimited,
    ClaudeCliUnavailable,
    classify_cli_error,
)

OK = json.dumps({"is_error": False, "result": "hello", "usage": {"input_tokens": 3, "output_tokens": 1},
                 "modelUsage": {"claude-sonnet-5": {"outputTokens": 1}}})


class _Proc:
    def __init__(self, script, calls):
        self._script = script
        self._calls = calls
        self.returncode = None
        self.pid = 4242

    async def communicate(self, data=None):
        self._calls.append({"stdin": data})
        rc, out, err, delay = self._script
        if delay:
            import asyncio
            await asyncio.sleep(delay)
        self.returncode = rc
        return out.encode(), err.encode()

    def kill(self):
        self.returncode = -9

    async def wait(self):
        return self.returncode


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    monkeypatch.setattr(claude_cli, "assert_subscription_auth", lambda binary, runner=None: None)
    state = {"scripts": [], "argvs": [], "calls": [], "sleeps": []}

    async def fake_exec(*argv, **kw):
        state["argvs"].append(list(argv))
        if not state["scripts"]:
            raise AssertionError("unexpected extra spawn")
        script = state["scripts"].pop(0)
        if isinstance(script, BaseException):
            raise script
        return _Proc(script, state["calls"])

    async def no_kill(proc):
        proc.returncode = -9

    monkeypatch.setattr(claude_cli.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(claude_cli, "_kill_process_tree", no_kill)

    async def fake_sleep(s):
        state["sleeps"].append(s)

    state["client"] = lambda **kw: ClaudeCliModelClient(binary="claude", sleep=fake_sleep, **kw)
    return state


def _req(system="You are a judge.", text="grade this transcript") -> ModelRequest:
    return ModelRequest(role=ModelRole.JUDGE, system=system, messages=[{"role": "user", "content": text}])


@pytest.mark.unit
async def test_prompt_goes_over_stdin_not_argv(harness):
    harness["scripts"] = [(0, OK, "", 0)]
    resp = await harness["client"]().complete(_req(text="SECRET-PROMPT-TEXT"))
    assert resp.text == "hello"
    assert resp.served_model == "claude-sonnet-5"
    assert resp.latency_s is not None
    assert harness["calls"][0]["stdin"] == b"SECRET-PROMPT-TEXT"
    assert not any("SECRET-PROMPT-TEXT" in a for a in harness["argvs"][0])


@pytest.mark.unit
async def test_overlong_system_prompt_is_refused_before_spawning(harness):
    with pytest.raises(ClaudeCliPromptTooLong):
        await harness["client"]().complete(_req(system="x" * 40_000))
    assert harness["argvs"] == []


@pytest.mark.unit
async def test_long_user_prompt_is_fine_over_stdin(harness):
    harness["scripts"] = [(0, OK, "", 0)]
    await harness["client"]().complete(_req(text="y" * 200_000))
    assert len(harness["calls"][0]["stdin"]) == 200_000


@pytest.mark.unit
async def test_rate_limit_is_retried_with_backoff(harness):
    limited = json.dumps({"is_error": True, "result": "API Error: 529 overloaded"})
    harness["scripts"] = [(1, limited, "", 0), (1, limited, "", 0), (0, OK, "", 0)]
    resp = await harness["client"](max_retries=2).complete(_req())
    assert resp.text == "hello"
    assert len(harness["argvs"]) == 3
    assert len(harness["sleeps"]) == 2 and harness["sleeps"][1] > harness["sleeps"][0]


@pytest.mark.unit
async def test_persistent_rate_limit_surfaces_as_rate_limited(harness):
    limited = json.dumps({"is_error": True, "result": "rate limit exceeded"})
    harness["scripts"] = [(1, limited, "", 0)] * 3
    with pytest.raises(ClaudeCliRateLimited):
        await harness["client"](max_retries=2).complete(_req())


@pytest.mark.unit
async def test_usage_limit_is_never_retried(harness):
    quota = json.dumps({"is_error": True, "result": "Claude AI usage limit reached|1760000000"})
    harness["scripts"] = [(1, quota, "", 0), (0, OK, "", 0)]
    with pytest.raises(ClaudeCliQuotaExhausted):
        await harness["client"](max_retries=3).complete(_req())
    assert len(harness["argvs"]) == 1  # exactly one attempt
    assert harness["sleeps"] == []


@pytest.mark.unit
async def test_timeout_raises_provider_timeout(harness):
    harness["scripts"] = [(0, OK, "", 5), (0, OK, "", 5)]
    with pytest.raises(ProviderTimeout):
        await harness["client"](timeout=0.05, max_retries=1).complete(_req())
    assert len(harness["argvs"]) == 2


@pytest.mark.unit
async def test_spawn_oserror_is_clean_and_not_retried(harness):
    harness["scripts"] = [OSError(206, "The filename or extension is too long")]
    with pytest.raises(ClaudeCliUnavailable, match="could not start"):
        await harness["client"](max_retries=3).complete(_req())
    assert len(harness["argvs"]) == 1


@pytest.mark.unit
async def test_nonzero_exit_with_plain_error_is_retried_then_unavailable(harness):
    harness["scripts"] = [(1, "", "boom", 0), (1, "", "boom", 0)]
    with pytest.raises(ClaudeCliUnavailable):
        await harness["client"](max_retries=1).complete(_req())
    assert len(harness["argvs"]) == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Claude AI usage limit reached|1760000000", ClaudeCliQuotaExhausted),
        ("You've hit your limit · resets at 3pm", ClaudeCliQuotaExhausted),
        ("API Error: 429 Too Many Requests", ClaudeCliRateLimited),
        ("Overloaded", ClaudeCliRateLimited),
        ("some other failure", ClaudeCliUnavailable),
    ],
)
def test_classify_cli_error(text, kind):
    assert type(classify_cli_error(text)) is kind


@pytest.mark.unit
def test_quota_exhaustion_is_fatal_not_isolatable():
    from fusion_first.errors import isolatable

    assert not isolatable(ClaudeCliQuotaExhausted("limit"))
    assert isolatable(ClaudeCliRateLimited("429"))
