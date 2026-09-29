"""The local web app's "Any model" backend: a scan names its target and grader by spec (openai:,
hf:, anthropic:, openai-compat: ...). Local servers only; cmd:/python: targets and the host grader
stay CLI/MCP-only. Offline: nothing here calls a model."""

from __future__ import annotations

import pytest

from fusion_first.integrations.live import LiveUnavailable
from fusion_first.web.clients import build_scan_kwargs
from fusion_first.web.settings import Settings

LOCAL = Settings(version="test", allow_local_backends=True)


@pytest.mark.unit
def test_spec_scans_need_a_local_server():
    with pytest.raises(LiveUnavailable, match="FUSION_ALLOW_LOCAL_BACKENDS"):
        build_scan_kwargs("live", Settings(version="test"), "spec", None, target_spec="openai:gpt-4o",
                          grader_spec="claude-cli")


@pytest.mark.unit
@pytest.mark.parametrize("target, grader, match", [
    ("cmd:python agent.py", "claude-cli", "command line"),
    ("python:bot", "claude-cli", "command line"),
    ("ollama:llama3.2:1b", "cmd:python judge.py", "command line"),
    ("ollama:llama3.2:1b", "host", "agent"),
    ("", "claude-cli", "target spec"),
    ("not a spec at all:::", "gpt", "grader"),
])
def test_spec_scans_refuse_what_only_the_cli_can_run(target, grader, match):
    with pytest.raises(LiveUnavailable, match=match):
        build_scan_kwargs("live", LOCAL, "spec", None, target_spec=target, grader_spec=grader)


@pytest.mark.unit
def test_hosted_providers_still_need_the_opt_in_and_key(monkeypatch):
    monkeypatch.delenv("FUSION_ALLOW_API_SPEND", raising=False)
    with pytest.raises(LiveUnavailable, match="FUSION_ALLOW_API_SPEND"):
        build_scan_kwargs("live", LOCAL, "spec", None, target_spec="openai:gpt-4o-mini", grader_spec="claude-cli")


@pytest.mark.unit
def test_a_spec_scan_builds_the_named_target_and_grader(monkeypatch):
    monkeypatch.setenv("FUSION_ALLOW_API_SPEND", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test_not_real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    kw = build_scan_kwargs("live", LOCAL, "spec", None, target_spec="hf:meta-llama/Llama-3.1-8B-Instruct",
                           grader_spec="openai:gpt-4o")
    assert kw["demonstration"] is False
    assert kw["target_model_id"] == "meta-llama/Llama-3.1-8B-Instruct"
    assert kw["judge_backend"] == "openai:gpt-4o" and kw["judge_model"] == "openai:gpt-4o"
    assert kw["judge_choice"].independence == "cross_family"
    assert kw["target_client"] is not None and kw["judge_client"] is not None
