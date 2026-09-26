"""The user's gate config is validated (typos fail closed) and the pre-deploy hook fails closed."""

from __future__ import annotations

import io
import json
import pathlib
import runpy
import subprocess
import types

import pytest
import yaml

from fusion.stats.gate import PolicyError, load_policy, validate_policy

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_committed_policy_is_valid():
    validate_policy(yaml.safe_load((ROOT / "evals/policy.yaml").read_text(encoding="utf-8")))
    assert load_policy("direct_prompt_injection")["min_judge_f1"] == 0.60


@pytest.mark.unit
@pytest.mark.parametrize(
    "data, match",
    [
        ({"defaults": {"min_judge_f": 0.9}}, "unknown key"),  # the typo that used to be ignored
        ({"defaults": {"min_judge_f1": 1.5}}, r"\[0, 1\]"),
        ({"defaults": {"min_judge_f1": True}}, r"\[0, 1\]"),
        ({"defaults": {"require_before_after_honesty": "SURE"}}, "one of"),
        ({"checks": {"prompt_injection": {"min_judge_f1": 0.7}}}, "unknown check"),
        ({"default": {}}, "top-level"),
        ({"checks": {"excessive_agency": {"max_unscored": 0.1}}}, "unknown key"),
    ],
)
def test_malformed_policy_fails_closed(tmp_path, data, match):
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(PolicyError, match=match):
        load_policy("excessive_agency", path)


def _run_gate(monkeypatch, command: str, run):
    mod = runpy.run_path(str(ROOT / "scripts/hooks/pre_deploy_gate.py"), run_name="gate")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_input": {"command": command}})))
    monkeypatch.setattr(subprocess, "run", run)
    return mod["main"]()


@pytest.mark.unit
def test_deploy_gate(monkeypatch):
    calls = []

    def green(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="[eval:PASS] a\n[eval:PASS] b\n")

    def red(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout="[eval:FAIL] a\n")

    def broken(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 180)

    assert _run_gate(monkeypatch, "ls -la", broken) == 0  # not a deploy: untouched
    assert _run_gate(monkeypatch, "modal deploy app/modal_app.py", green) == 0
    assert calls[0][-2:] == ["--check", "all"]  # every check is gated
    assert _run_gate(monkeypatch, "modal deploy app/modal_app.py", red) == 2
    assert _run_gate(monkeypatch, "modal deploy app/modal_app.py", broken) == 2  # fail closed
