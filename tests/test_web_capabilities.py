"""/api/version reports only what a web scan can actually start AND grade on this server: the claude CLI,
a local grader that met its pre-registered floor, or a hosted provider with its key and the spend opt-in."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fusion_first.web.factory import create_app
from fusion_first.web.settings import Settings

KEY_ENVS = ("OPENAI_API_KEY", "HF_TOKEN", "OPENROUTER_API_KEY", "TOGETHER_API_KEY", "GROQ_API_KEY",
            "FIREWORKS_API_KEY", "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture
def machine(monkeypatch):
    """A machine with nothing set up; each test switches on what it needs."""
    from fusion_first.model.providers import claude_cli, ollama
    from fusion_first.validate import prereg

    for env in (*KEY_ENVS, "FUSION_ALLOW_API_SPEND"):
        monkeypatch.delenv(env, raising=False)
    state = {"cli": (False, "the `claude` CLI is not logged in"), "models": None, "floor": set()}
    monkeypatch.setattr(claude_cli, "claude_cli_ready", lambda *a, **k: state["cli"])
    monkeypatch.setattr(ollama, "ollama_available", lambda *a, **k: state["models"] is not None)
    monkeypatch.setattr(ollama, "ollama_models", lambda *a, **k: [{"name": m} for m in state["models"] or []])
    monkeypatch.setattr(prereg, "local_grader_status",
                        lambda m: {"model": m, "measured": True, "meets_floor": m in state["floor"]})
    return state


def backends(local=True):
    app = create_app(settings=Settings(version="test", allow_local_backends=local))
    return TestClient(app).get("/api/version").json()["backends"]


@pytest.mark.integration
def test_nothing_set_up_reports_no_grader_and_no_spec(machine):
    b = backends()
    assert b["graders"] == [] and b["hosted_providers"] == []
    assert b["spec"] is False


@pytest.mark.integration
def test_ollama_models_alone_are_not_a_grader(machine):
    machine["models"] = ["llama3.2:1b", "qwen2.5:7b"]  # qwen2.5:7b measured below the floor
    b = backends()
    assert b["ollama_models"] == ["llama3.2:1b", "qwen2.5:7b"]
    assert b["graders"] == [] and b["spec"] is False


@pytest.mark.integration
def test_a_local_grader_that_met_its_floor_counts(machine):
    machine["models"] = ["llama3.2:1b", "qwen2.5:7b"]
    machine["floor"] = {"qwen2.5:7b"}
    b = backends()
    assert b["graders"] == ["ollama-prob:qwen2.5:7b"]
    assert b["spec"] is True


@pytest.mark.integration
def test_logged_in_cli_is_the_first_grader(machine):
    machine["cli"] = (True, "ok")
    assert backends()["graders"] == ["claude-cli"]


@pytest.mark.integration
def test_a_hosted_key_grades_only_with_the_spend_opt_in(machine, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-key")
    b = backends()
    assert b["hosted_keys"] == ["openai"] and b["hosted_providers"] == [] and b["spec"] is False
    monkeypatch.setenv("FUSION_ALLOW_API_SPEND", "1")
    b = backends()
    assert b["hosted_providers"] == ["openai"] and b["spend_opt_in"] is True and b["spec"] is True


@pytest.mark.integration
def test_demo_only_server_reports_no_live_capability(machine, monkeypatch):
    machine["cli"] = (True, "ok")
    machine["models"] = ["qwen2.5:7b"]
    machine["floor"] = {"qwen2.5:7b"}
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-key")
    monkeypatch.setenv("FUSION_ALLOW_API_SPEND", "1")
    b = backends(local=False)
    assert b["graders"] == [] and b["hosted_providers"] == [] and b["hosted_keys"] == []
    assert b["spec"] is False and b["local_backends_enabled"] is False
