"""Zero spend through the `claude` CLI: paid-auth env vars are stripped from every child process, and
`auth status` must report subscription (claude.ai, first-party) auth before any call."""

from __future__ import annotations

import json
import subprocess

import pytest

from fusion_first.model.providers import claude_cli
from fusion_first.model.providers.claude_cli import (
    ClaudeCliModelClient,
    PaidAuthRefused,
    assert_subscription_auth,
)

_SUB = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "max"}


def _runner(payload: dict | str, returncode: int = 0, calls: list | None = None):
    def run(argv, **kw):
        if calls is not None:
            calls.append((argv, kw))
        out = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.CompletedProcess(argv, returncode, stdout=out, stderr="")

    return run


@pytest.fixture(autouse=True)
def _fresh_auth_cache():
    claude_cli._AUTH_OK.clear()
    yield
    claude_cli._AUTH_OK.clear()


@pytest.mark.unit
@pytest.mark.parametrize(
    "var",
    [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "OPENAI_API_KEY",
    ],
)
def test_paid_auth_env_is_stripped_from_child(monkeypatch, var):
    monkeypatch.setenv(var, "sk-should-never-reach-the-child")
    env = ClaudeCliModelClient._build_env()
    assert var not in env


@pytest.mark.unit
def test_subscription_auth_passes():
    calls: list = []
    assert_subscription_auth("claude", runner=_runner(_SUB, calls=calls))
    argv, kw = calls[0]
    assert argv[1:] == ["auth", "status"]
    assert "ANTHROPIC_API_KEY" not in kw["env"]


@pytest.mark.unit
def test_auth_result_is_cached_per_binary():
    calls: list = []
    assert_subscription_auth("claude", runner=_runner(_SUB, calls=calls))
    assert_subscription_auth("claude", runner=_runner(_SUB, calls=calls))
    assert len(calls) == 1


@pytest.mark.unit
def test_cached_pass_expires(monkeypatch):
    calls: list = []
    assert_subscription_auth("claude", runner=_runner(_SUB, calls=calls))
    real = claude_cli.time.monotonic
    monkeypatch.setattr(claude_cli.time, "monotonic", lambda: real() + claude_cli.AUTH_TTL_S + 1)
    assert_subscription_auth("claude", runner=_runner(_SUB, calls=calls))
    assert len(calls) == 2


@pytest.mark.unit
def test_logged_out_cli_gets_a_login_hint():
    logged_out = {"loggedIn": False, "authMethod": "none", "apiProvider": "firstParty"}
    with pytest.raises(PaidAuthRefused, match="claude auth login"):
        assert_subscription_auth("claude", runner=_runner(logged_out, returncode=1))


@pytest.mark.unit
def test_timed_out_auth_check_is_refused():
    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout", 30))

    with pytest.raises(PaidAuthRefused):
        assert_subscription_auth("claude", runner=slow)


@pytest.mark.unit
def test_bounded_runner_kills_a_hung_child():
    import sys
    import time as _t

    t0 = _t.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        claude_cli._run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1, env=None)
    assert _t.monotonic() - t0 < 15


@pytest.mark.unit
@pytest.mark.parametrize(
    "status",
    [
        {**_SUB, "authMethod": "api_key"},
        {**_SUB, "authMethod": "apiKeyHelper"},
        {**_SUB, "apiProvider": "bedrock"},
        {**_SUB, "apiProvider": "vertex"},
        {**_SUB, "loggedIn": False},
        {"loggedIn": True},
    ],
)
def test_non_subscription_auth_is_refused(status):
    with pytest.raises(PaidAuthRefused):
        assert_subscription_auth("claude", runner=_runner(status))


@pytest.mark.unit
def test_unreadable_auth_status_is_refused():
    with pytest.raises(PaidAuthRefused):
        assert_subscription_auth("claude", runner=_runner("not json"))
    with pytest.raises(PaidAuthRefused):
        assert_subscription_auth("claude", runner=_runner(_SUB, returncode=1))


@pytest.mark.unit
def test_refusal_is_not_cached():
    with pytest.raises(PaidAuthRefused):
        assert_subscription_auth("claude", runner=_runner({**_SUB, "authMethod": "api_key"}))
    assert_subscription_auth("claude", runner=_runner(_SUB))  # fixed auth is re-checked, passes


@pytest.mark.unit
async def test_complete_refuses_before_spawning_when_auth_is_paid(monkeypatch):
    def refuse(binary, runner=None):
        raise PaidAuthRefused("metered auth")

    spawned = []

    async def fake_exec(*a, **kw):  # pragma: no cover - must never run
        spawned.append(a)
        raise AssertionError("spawned a paid call")

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)  # exercise the auth gate itself
    monkeypatch.setattr(claude_cli, "assert_subscription_auth", refuse)
    monkeypatch.setattr(claude_cli.asyncio, "create_subprocess_exec", fake_exec)
    client = ClaudeCliModelClient(binary="claude")
    from fusion_first.model.client import ModelRequest, ModelRole

    req = ModelRequest(role=ModelRole.JUDGE, system="s", messages=[{"role": "user", "content": "x"}])
    with pytest.raises(PaidAuthRefused):
        await client.complete(req)
    assert spawned == []


@pytest.mark.unit
def test_cli_ready_reports_a_logged_out_cli_as_not_ready(monkeypatch):
    from fusion_first.model.providers.claude_cli import claude_cli_ready

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    ready, reason = claude_cli_ready("claude", runner=_runner({"loggedIn": False, "authMethod": "none"}, returncode=1))
    assert ready is False and "not logged in" in reason


@pytest.mark.unit
def test_cli_ready_on_subscription_auth(monkeypatch):
    from fusion_first.model.providers.claude_cli import claude_cli_ready

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    assert claude_cli_ready("claude", runner=_runner(_SUB)) == (True, "ok")


@pytest.mark.unit
def test_cli_ready_is_false_offline_without_running_anything(monkeypatch):
    from fusion_first.model.providers.claude_cli import claude_cli_ready

    monkeypatch.setenv("FUSION_OFFLINE", "1")
    calls = []
    ready, _ = claude_cli_ready("claude", runner=_runner(_SUB, calls=calls))
    assert ready is False and calls == []
