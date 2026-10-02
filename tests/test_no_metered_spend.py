"""No code path reaches a metered model API unless the user opted in (`--backend api` AND
FUSION_ALLOW_API_SPEND=1); an API key in the environment is never consent to spend."""

from __future__ import annotations

import pytest

import fusion_first.integrations.live as live

METERED = ("AnthropicModelClient", "OpenAIModelClient")


def _inner_name(client) -> str:
    return type(getattr(client, "inner", client)).__name__


@pytest.fixture
def ambient_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-ambient")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-ambient")
    monkeypatch.delenv("FUSION_TARGET_BACKEND", raising=False)
    monkeypatch.delenv(live.METERED_OPT_IN_ENV, raising=False)
    monkeypatch.setattr("fusion_first.model.providers.claude_cli.claude_cli_ready", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr("fusion_first.model.providers.ollama.ollama_available", lambda base_url=None: True)


@pytest.mark.unit
@pytest.mark.parametrize("prefer", [None, "auto", "cli", "ollama"])
def test_keyless_backends_never_build_metered_clients(ambient_keys, prefer):
    target, judge, _jid, _choice = live.build_live_clients("llama3.2:1b", prefer=prefer)
    assert _inner_name(target) not in METERED
    assert _inner_name(judge) not in METERED
    assert _inner_name(judge) == "ClaudeCliModelClient"


@pytest.mark.unit
def test_api_backend_without_opt_in_is_refused(ambient_keys):
    with pytest.raises(live.LiveUnavailable, match=live.METERED_OPT_IN_ENV):
        live.build_live_clients(prefer="api")


@pytest.mark.unit
def test_api_backend_with_explicit_opt_in_builds_metered(ambient_keys, monkeypatch):
    monkeypatch.setenv(live.METERED_OPT_IN_ENV, "1")
    target, judge, _jid, _choice = live.build_live_clients(prefer="api")
    assert _inner_name(target) == "AnthropicModelClient"
    assert _inner_name(judge) in METERED


@pytest.mark.unit
def test_opt_in_alone_does_not_make_auto_metered(ambient_keys, monkeypatch):
    monkeypatch.setenv(live.METERED_OPT_IN_ENV, "1")
    target, judge, _jid, _choice = live.build_live_clients(prefer="auto")
    assert _inner_name(target) not in METERED and _inner_name(judge) not in METERED


@pytest.mark.unit
def test_no_cli_and_ambient_keys_fails_closed_not_metered(ambient_keys, monkeypatch):
    monkeypatch.setattr("fusion_first.model.providers.claude_cli.claude_cli_ready",
                        lambda *a, **k: (False, "the `claude` CLI isn't installed here"))
    for prefer in (None, "auto", "cli", "ollama"):
        with pytest.raises(live.LiveUnavailable):
            live.build_live_clients("llama3.2:1b", prefer=prefer)


@pytest.mark.unit
async def test_mcp_auto_mode_with_ambient_keys_is_not_metered(ambient_keys, monkeypatch):
    from fusion_first.integrations import agent_tools

    kwargs, mode = agent_tools._resolve_live_kwargs("auto", None, None)
    assert mode == "live"
    assert _inner_name(kwargs["target_client"]) not in METERED
    assert _inner_name(kwargs["judge_client"]) not in METERED


@pytest.mark.unit
@pytest.mark.parametrize("backend", ["ollama", "cli", None])
def test_web_app_keyless_backends_ignore_server_keys(monkeypatch, backend):
    from fusion_first.web.clients import LiveUnavailable, build_scan_kwargs
    from fusion_first.web.settings import Settings

    monkeypatch.delenv(live.METERED_OPT_IN_ENV, raising=False)
    monkeypatch.setattr("fusion_first.model.providers.claude_cli.claude_cli_ready", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr("fusion_first.model.providers.ollama.ollama_available", lambda base_url=None: True)
    settings = Settings(anthropic_api_key="sk-ant-fake", openai_api_key="sk-fake", allow_local_backends=True)
    if backend is None:
        with pytest.raises(LiveUnavailable):
            build_scan_kwargs("live", settings, backend="api")
        return
    kw = build_scan_kwargs("live", settings, backend=backend, target_model="llama3.2:1b")
    assert _inner_name(kw["target_client"]) not in METERED
    assert _inner_name(kw["judge_client"]) not in METERED


@pytest.mark.unit
@pytest.mark.parametrize("backend", [None, "auto", "cli", "ollama"])
def test_web_app_local_backends_are_off_by_default(monkeypatch, backend):
    """A public server must never let visitors drive the host's subscription or CPU."""
    from fusion_first.web.clients import LiveUnavailable, build_scan_kwargs
    from fusion_first.web.settings import Settings

    monkeypatch.setattr("fusion_first.model.providers.claude_cli.claude_cli_ready", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr("fusion_first.model.providers.ollama.ollama_available", lambda base_url=None: True)
    with pytest.raises(LiveUnavailable, match="FUSION_ALLOW_LOCAL_BACKENDS"):
        build_scan_kwargs("live", Settings(), backend=backend)


@pytest.mark.unit
def test_offline_switch_disables_real_clients(monkeypatch):
    """FUSION_OFFLINE=1 (set by conftest for non-live tests) makes both real providers unavailable."""
    from fusion_first.model.providers.claude_cli import claude_cli_available
    from fusion_first.model.providers.ollama import ollama_available

    monkeypatch.setenv("FUSION_OFFLINE", "1")
    assert claude_cli_available("claude") is False
    assert ollama_available() is False


@pytest.mark.unit
def test_live_scan_kwargs_disclose_the_judge(ambient_keys):
    kw = live.build_live_scan_kwargs("llama3.2:1b", prefer="ollama")
    assert kw["judge_backend"] == "claude_cli"
    assert kw["sampling_pinned"] is False  # the CLI cannot pin temperature
    assert kw["judge_choice"].independence == "cross_family"
