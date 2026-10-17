"""The committed example run (examples/verified-run: llama3.2:1b, graded by Claude Code host subagents)
re-derives exactly, offline and without its .secret, and verify catches drift. CI also runs
`fusion run verify --workspace examples/verified-run latest` as its own step."""

from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from fusion_first.cli import main
from fusion_first.runs import service

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "examples" / "verified-run"
RUN = WORKSPACE / ".fusion" / "runs" / "f9388f6e9b11"
KEPT = {"plan.json", "prompt.txt", "target.cassette.json", "judge.requests.json", "judge.cassette.json",
        "tasks.json", "state.json", "result.json", "report.html"}


def _files(d: pathlib.Path) -> set[str]:
    return {p.name for p in d.iterdir()}


def _verify(workspace: pathlib.Path, capsys, *extra: str) -> tuple[int, dict]:
    code = main(["run", "verify", "--workspace", str(workspace), "latest", "--json", *extra])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.integration
def test_the_committed_run_keeps_only_what_verify_reads():
    """No .secret (the task-id key, read only during collect), leases, heartbeat or lock file."""
    assert _files(RUN) == KEPT


@pytest.mark.integration
def test_the_committed_run_verifies_offline_without_its_secret(capsys):
    rd = service.resolve_run(WORKSPACE, "latest")
    assert rd.root.resolve() == RUN.resolve() and not rd.secret_path.exists()
    code, res = _verify(WORKSPACE, capsys, "--prompt", str(WORKSPACE / "prompt.txt"))
    assert (code, res) == (0, {"ok": True, "reason": ""})
    assert _files(RUN) == KEPT  # verify leaves nothing behind, its lock file included


@pytest.mark.integration
def test_the_run_is_of_the_committed_prompt():
    plan = json.loads((RUN / "plan.json").read_text(encoding="utf-8"))
    assert (RUN / "prompt.txt").read_bytes() == (WORKSPACE / "prompt.txt").read_bytes()
    assert plan["target"] == "ollama:llama3.2:1b" and plan["grader"] == "host" and plan["calibration"]


@pytest.mark.integration
def test_the_result_is_real_and_measures_the_grader_in_run():
    result = json.loads((RUN / "result.json").read_text(encoding="utf-8"))
    assert result["demonstration"] is False and result["partial"] is False
    assert sorted(c["check"] for c in result["cards"]) == sorted(result["run"]["checks"])
    for card in result["cards"]:
        assert card["demonstration"] is False
        assert card["judge_accuracy"] and card["judge_accuracy"]["n"] > 0, card["check"]
    assert [g["check"] for g in result["grader_gate"]] == [c["check"] for c in result["cards"]]


@pytest.mark.integration
@pytest.mark.parametrize("name", ["judge.cassette.json", "result.json"])
def test_verify_fails_on_drift(tmp_path, capsys, name):
    """An edited recording breaks the commitment; an edited result no longer re-derives."""
    ws = tmp_path / "ws"
    shutil.copytree(WORKSPACE, ws)
    path = ws / RUN.relative_to(WORKSPACE) / name
    if name == "result.json":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["overall_grade"] = "A" if data["overall_grade"] != "A" else "B"
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    code, res = _verify(ws, capsys)
    assert code == 1 and res["ok"] is False and res["reason"]


@pytest.mark.unit
@pytest.mark.parametrize("rel", ["README.md", "docs/RUN_LOCALLY.md", ".github/workflows/ci.yml"])
def test_the_docs_and_ci_run_the_same_verify_command(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "fusion run verify --workspace examples/verified-run latest" in text


@pytest.mark.unit
def test_git_keeps_the_recorded_bytes():
    """verify hashes the recordings byte for byte, so a core.autocrlf checkout must not rewrite them."""
    rules = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "examples/verified-run/** -text" in rules
