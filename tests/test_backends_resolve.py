"""Target/grader spec parsing, the zero-spend refusals, and `doctor` — all offline."""

from __future__ import annotations

import json
import types

import pytest

from fusion.backends.resolve import (
    BackendUnavailable,
    GraderSpec,
    SpecError,
    TargetSpec,
    build_grader_client,
    build_target_client,
    doctor,
    parse_grader,
    parse_target,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "spec, expected",
    [
        ("ollama:llama3.2:1b", TargetSpec("ollama", "llama3.2:1b")),
        ("llama3.2:1b", TargetSpec("ollama", "llama3.2:1b")),  # bare non-Claude id -> local
        ("qwen2.5:7b", TargetSpec("ollama", "qwen2.5:7b")),
        ("claude-cli:claude-haiku-4-5", TargetSpec("claude_cli", "claude-haiku-4-5")),
        ("cli:claude-haiku-4-5", TargetSpec("claude_cli", "claude-haiku-4-5")),
        ("claude-haiku-4-5", TargetSpec("claude_cli", "claude-haiku-4-5")),  # allowlisted Claude id
        ("api:claude-haiku-4-5", TargetSpec("api", "claude-haiku-4-5")),
    ],
)
def test_parse_target(spec, expected):
    assert parse_target(spec) == expected


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", "ollama:", "ollama:claude-haiku-4-5", "ollama:gpt-4o"])
def test_parse_target_rejects(bad):
    with pytest.raises(SpecError):
        parse_target(bad)


@pytest.mark.unit
def test_parse_grader():
    assert parse_grader("host") == GraderSpec("host")
    assert parse_grader("") == GraderSpec("host")
    assert parse_grader("claude-cli") == GraderSpec("claude_cli")
    assert parse_grader("claude-cli:claude-opus-4-8") == GraderSpec("claude_cli", "claude-opus-4-8")
    assert parse_grader("ollama-prob:qwen2.5:7b") == GraderSpec("ollama_prob", "qwen2.5:7b")
    assert parse_grader("ollama:qwen2.5:7b") == GraderSpec("ollama_json", "qwen2.5:7b")
    assert parse_grader("host").external and not parse_grader("claude-cli").external
    for bad in ("api:claude-sonnet-5", "ollama-prob", "gpt"):
        with pytest.raises(SpecError):
            parse_grader(bad)


@pytest.mark.unit
def test_api_target_is_refused_even_with_a_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    with pytest.raises(BackendUnavailable, match="metered|disabled"):
        build_target_client(parse_target("api:claude-haiku-4-5"))


@pytest.mark.unit
def test_offline_refuses_real_backends():
    # conftest sets FUSION_OFFLINE=1 for every non-live test: nothing real can be built.
    for spec in ("ollama:llama3.2:1b", "claude-cli:claude-haiku-4-5"):
        with pytest.raises(BackendUnavailable):
            build_target_client(parse_target(spec))
    for g in ("claude-cli", "ollama-prob:qwen2.5:7b"):
        with pytest.raises(BackendUnavailable):
            build_grader_client(parse_grader(g))
    with pytest.raises(SpecError):
        build_grader_client(parse_grader("host"))


@pytest.mark.unit
def test_doctor_offline_recommends_the_host_grader():
    d = doctor()
    assert d["offline"] is True and d["zero_spend"] is True
    assert d["backends"]["claude_cli"]["available"] is False
    assert d["backends"]["api"]["available"] is False
    assert d["recommended"]["grader"] == "host"
    json.dumps(d)  # plain JSON for MCP/CLI


@pytest.mark.unit
def test_doctor_reports_a_refused_subscription(monkeypatch):
    import fusion.model.providers.claude_cli as cc

    monkeypatch.delenv("FUSION_OFFLINE", raising=False)
    monkeypatch.setattr(cc, "_AUTH_OK", {})
    monkeypatch.setenv("FUSION_CLAUDE_BIN", "claude-fake")
    import fusion.model.providers.ollama as ol

    monkeypatch.setattr(ol, "ollama_available", lambda *a, **k: False)

    def runner(*a, **k):
        out = {"loggedIn": True, "authMethod": "apiKey", "apiProvider": "firstParty"}
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(out))

    d = doctor(auth_runner=runner)
    assert d["backends"]["claude_cli"]["subscription"].startswith("refused")
    assert d["recommended"]["grader"] == "host"  # a refused CLI is never recommended
    assert any("subscription" in h for h in d["hints"])
