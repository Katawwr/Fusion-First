"""The CLI-backed ModelClient's pure helpers against captured-stdout fixtures, plus one opt-in live
smoke (`@pytest.mark.live`)."""

from __future__ import annotations

import json

import pytest

from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.providers.claude_cli import (
    ClaudeCliModelClient,
    ClaudeCliUnavailable,
    claude_cli_available,
)

# A representative `claude -p ... --output-format json` envelope.
_CLI_ENVELOPE = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": '{"criteria": [], "rationale": "ok", "confidence": 0.9}',
        "usage": {"input_tokens": 12, "output_tokens": 34},
    }
)


def _judge_req(**kw) -> ModelRequest:
    base = dict(role=ModelRole.JUDGE, system="You are a judge.", messages=[{"role": "user", "content": "grade this"}])
    base.update(kw)
    return ModelRequest(**base)


def _target_req(**kw) -> ModelRequest:
    base = dict(
        role=ModelRole.TARGET,
        system="You are a support bot.",
        messages=[{"role": "user", "content": "hi"}],
        model_id="claude-haiku-4-5",
    )
    base.update(kw)
    return ModelRequest(**base)


# -- _cli_model: allowlist + CLI mapping --------------------------------------------------------


def test_cli_model_maps_haiku_target_to_dated_id():
    c = ClaudeCliModelClient()
    assert c._cli_model(_target_req()) == "claude-haiku-4-5-20251001"


def test_cli_model_default_judge_is_sonnet():
    # A default judge request has model_id=None (the cassette-key linchpin) -> role default sonnet-5.
    c = ClaudeCliModelClient()
    assert c._cli_model(_judge_req()) == "claude-sonnet-5"


def test_judge_model_override_changes_model_not_request():
    # Override the judge tier (e.g. opus) WITHOUT touching the request's model_id/cache key.
    req = _judge_req()
    key_before = req.cache_key()
    c = ClaudeCliModelClient(judge_model="claude-opus-4-8")
    assert c._cli_model(req) == "claude-opus-4-8"
    assert req.cache_key() == key_before  # request untouched


def test_cli_model_rejects_openai_model():
    # gpt-4o is allowlisted but cannot be served by the claude CLI -> explicit unavailable.
    c = ClaudeCliModelClient()
    with pytest.raises(ClaudeCliUnavailable):
        c._cli_model(_target_req(model_id="gpt-4o"))


def test_cli_model_rejects_unallowlisted_model():
    c = ClaudeCliModelClient()
    with pytest.raises((ClaudeCliUnavailable, ValueError)):
        c._cli_model(_target_req(model_id="gpt-5-turbo"))


# -- _flatten_messages -------------------------------------------------------------------------


def test_flatten_single_user_turn_is_verbatim():
    assert ClaudeCliModelClient._flatten_messages([{"role": "user", "content": "just this"}]) == "just this"


def test_flatten_multi_turn_is_labeled_transcript():
    out = ClaudeCliModelClient._flatten_messages(
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
    )
    assert "User: first" in out and "Assistant: reply" in out and "User: second" in out


# -- _build_argv -------------------------------------------------------------------------------


def test_build_argv_has_clean_context_flags():
    c = ClaudeCliModelClient()
    req = _target_req()
    argv = c._build_argv("claude", req, "claude-haiku-4-5-20251001")
    assert argv[:2] == ["claude", "-p"]
    assert "hi" not in argv  # the prompt goes over stdin, never argv (Windows command-line limit)
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    # clean-context + headless flags must be present
    assert "--tools" in argv and argv[argv.index("--tools") + 1] == ""
    assert "--setting-sources" in argv and argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5-20251001"
    assert argv[argv.index("--system-prompt") + 1] == "You are a support bot."


def test_build_argv_appends_json_nudge_only_with_schema():
    c = ClaudeCliModelClient()
    plain = c._build_argv("claude", _judge_req(), "claude-sonnet-5")
    assert "JSON" not in plain[plain.index("--system-prompt") + 1]

    schema_req = _judge_req(response_schema={"type": "object", "properties": {}})
    withschema = c._build_argv("claude", schema_req, "claude-sonnet-5")
    assert "JSON" in withschema[withschema.index("--system-prompt") + 1]


# -- _build_env: nested-session guard bypass ---------------------------------------------------


def test_build_env_unsets_nested_guard(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SSE_PORT", "8080")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("KEEP_ME", "yes")
    env = ClaudeCliModelClient._build_env()
    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_SSE_PORT" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    assert env.get("KEEP_ME") == "yes"


# -- _parse_cli_json ---------------------------------------------------------------------------


def test_parse_cli_json_extracts_result_and_usage():
    resp = ClaudeCliModelClient._parse_cli_json(_CLI_ENVELOPE, "claude-sonnet-5")
    assert resp.text.startswith("{") and "rationale" in resp.text
    assert resp.model == "claude-sonnet-5"
    assert resp.input_tokens == 12 and resp.output_tokens == 34
    assert resp.stop_reason == "cli"


def test_parse_cli_json_raises_on_error_envelope():
    bad = json.dumps({"is_error": True, "result": "rate limit"})
    with pytest.raises(ClaudeCliUnavailable):
        ClaudeCliModelClient._parse_cli_json(bad, "claude-sonnet-5")


def test_parse_cli_json_empty_result_is_empty_text():
    # Empty text makes the judge fail CLOSED downstream (JudgeParseError), never silently "no issue".
    env = json.dumps({"is_error": False, "result": ""})
    resp = ClaudeCliModelClient._parse_cli_json(env, "claude-sonnet-5")
    assert resp.text == ""


def test_missing_binary_raises_unavailable(monkeypatch):
    monkeypatch.delenv("FUSION_CLAUDE_BIN", raising=False)
    monkeypatch.setattr("fusion_first.model.providers.claude_cli.shutil.which", lambda _: None)
    c = ClaudeCliModelClient(binary=None)
    with pytest.raises(ClaudeCliUnavailable):
        c._resolve_binary()
    assert isinstance(claude_cli_available(), bool)


# -- opt-in live smoke (real subscription CLI call) --------------------------------------------


@pytest.mark.live
async def test_live_smoke_returns_text():
    if not claude_cli_available():
        pytest.skip("claude CLI not available")
    c = ClaudeCliModelClient()
    req = _target_req(messages=[{"role": "user", "content": "Reply with exactly: PONG"}])
    resp = await c.complete(req)
    assert "PONG" in resp.text.upper()


@pytest.mark.unit
def test_windows_shell_shims_are_refused():
    """A prompt with `"` and `&` passed through a .cmd/.bat shim would be re-parsed by cmd.exe and
    could run commands; only a native executable may receive the prompt under test."""
    from fusion_first.model.providers.claude_cli import (
        ClaudeCliModelClient,
        ClaudeCliUnavailable,
        refuse_shell_shim,
    )

    for shim in (r"C:\npm\claude.cmd", r"C:\npm\CLAUDE.BAT"):
        with pytest.raises(ClaudeCliUnavailable, match="shell shim"):
            refuse_shell_shim(shim, os_name="nt")
    refuse_shell_shim(r"C:\Users\x\.local\bin\claude.exe", os_name="nt")  # native: fine
    refuse_shell_shim("/usr/local/bin/claude.cmd", os_name="posix")  # no cmd.exe on posix
    import os

    if os.name == "nt":
        with pytest.raises(ClaudeCliUnavailable, match="shell shim"):
            ClaudeCliModelClient(binary=r"C:\npm\claude.cmd")._resolve_binary()
