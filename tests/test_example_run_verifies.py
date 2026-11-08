"""The committed example runs re-derive exactly, offline and without their .secret, and verify catches drift:
examples/verified-run (llama3.2:1b, corpus v1, the four safety checks) and examples/verified-run-toolloop
(qwen2.5:7b through the tool loop, --corpus v2, Full tier, the two agentic checks), both graded by Claude Code
host subagents. CI also runs `fusion run verify --workspace <workspace> latest` for each as its own step."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import shutil

import pytest

from fusion_first.attacks.templates import get_templates
from fusion_first.cli import main
from fusion_first.runs import service

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEPT = {"plan.json", "prompt.txt", "target.cassette.json", "judge.requests.json", "judge.cassette.json",
        "tasks.json", "state.json", "result.json", "report.html"}


@dataclasses.dataclass(frozen=True)
class Example:
    name: str
    run_id: str
    target: str
    version: str
    checks: tuple[str, ...]
    tier: str

    @property
    def workspace(self) -> pathlib.Path:
        return ROOT / "examples" / self.name

    @property
    def run(self) -> pathlib.Path:
        return self.workspace / ".fusion" / "runs" / self.run_id

    @property
    def verify_command(self) -> str:
        return f"fusion run verify --workspace examples/{self.name} latest"


EXAMPLES = [
    Example("verified-run", "f9388f6e9b11", "ollama:llama3.2:1b", "v1",
            ("data_exfiltration", "direct_prompt_injection", "excessive_agency", "system_prompt_leakage"), tier="quick"),
    Example("verified-run-toolloop", "45eb15bc9e0e", "ollama:qwen2.5:7b", "v2",
            ("data_exfiltration", "excessive_agency"), tier="full"),
]
TOOLLOOP = EXAMPLES[1]
each_example = pytest.mark.parametrize("ex", EXAMPLES, ids=[e.name for e in EXAMPLES])


def _files(d: pathlib.Path) -> set[str]:
    return {p.name for p in d.iterdir()}


def _json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify(workspace: pathlib.Path, capsys, *extra: str) -> tuple[int, dict]:
    code = main(["run", "verify", "--workspace", str(workspace), "latest", "--json", *extra])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.integration
@each_example
def test_the_committed_run_keeps_only_what_verify_reads(ex):
    """No .secret (the task-id key, read only during collect), leases, heartbeat or lock file."""
    assert _files(ex.run) == KEPT


@pytest.mark.integration
@each_example
def test_the_committed_run_verifies_offline_without_its_secret(ex, capsys):
    rd = service.resolve_run(ex.workspace, "latest")
    assert rd.root.resolve() == ex.run.resolve() and not rd.secret_path.exists()
    code, res = _verify(ex.workspace, capsys, "--prompt", str(ex.workspace / "prompt.txt"))
    assert (code, res) == (0, {"ok": True, "reason": ""})
    assert _files(ex.run) == KEPT  # verify leaves nothing behind, its lock file included


@pytest.mark.integration
@each_example
def test_the_run_is_of_the_committed_prompt_and_corpus(ex):
    plan = _json(ex.run / "plan.json")
    assert (ex.run / "prompt.txt").read_bytes() == (ex.workspace / "prompt.txt").read_bytes()
    assert plan["target"] == ex.target and plan["grader"] == "host" and plan["calibration"]
    assert plan["version"] == ex.version and sorted(plan["checks"]) == sorted(ex.checks)
    assert plan["tier"] == ex.tier


@pytest.mark.integration
@each_example
def test_the_result_is_real_and_measures_the_grader_in_run(ex):
    result = _json(ex.run / "result.json")
    assert result["demonstration"] is False and result["partial"] is False
    assert sorted(c["check"] for c in result["cards"]) == sorted(result["run"]["checks"]) == sorted(ex.checks)
    for card in result["cards"]:
        assert card["demonstration"] is False
        assert card["judge_accuracy"] and card["judge_accuracy"]["n"] > 0, card["check"]
    assert [g["check"] for g in result["grader_gate"]] == [c["check"] for c in result["cards"]]


@pytest.mark.integration
def test_the_tool_loop_run_holds_real_tool_calls_their_oracle_check_and_their_accounting():
    """The qwen2.5:7b run went through the loop: the target recording carries native tool calls, the stored
    accounting block counts them, the oracle cross-check ran on them, and both arms were attacked."""
    ex = TOOLLOOP
    plan, result = _json(ex.run / "plan.json"), _json(ex.run / "result.json")
    assert plan["fix_arm"] is True and result["run"]["version"] == "v2"
    state = _json(ex.run / "state.json")  # Full tier: every v2 template of each check was attacked...
    assert state["total"] == state["completed"] == sum(len(get_templates(c, "v2")) for c in ex.checks)
    for card in result["cards"]:  # ...and scored as an as-written / with-fix pair
        n = len(get_templates(card["check"], "v2"))
        assert card["before_after"]["n_pairs"] == card["trust"]["n_scored"] == n, card["check"]
    with_calls = sum(1 for e in _json(ex.run / "target.cassette.json").values() if e.get("tool_calls"))
    assert with_calls > 0
    acc = result["accounting"]
    assert acc["responses_with_tool_calls"] == with_calls and acc["target_calls"] >= with_calls
    assert acc["latency_s"]["n_with_latency"] == acc["target_calls"] > 0 and acc["output_tokens"] > 0
    for gate in result["grader_gate"]:
        agreement = gate["oracle_agreement"]
        assert agreement["n"] > 0 and agreement["unanswered"] == 0, gate["check"]
    transcripts = [json.dumps(r) for r in _json(ex.run / "judge.requests.json").values()]
    assert any("[ASSISTANT calls " in t for t in transcripts)


@pytest.mark.unit
def test_the_docs_say_the_tool_loop_grade_is_withheld_only_while_its_result_says_so():
    """The living docs state that the example's data_exfiltration grade is withheld by the in-run grader gate (one
    oracle-confirmed violation called clean). A re-run whose grader clears the gate must take the sentence out, and
    the sentence may not appear without the evidence."""
    result = _json(TOOLLOOP.run / "result.json")
    gate = next(g for g in result["grader_gate"] if g["check"] == "data_exfiltration")
    card = next(c for c in result["cards"] if c["check"] == "data_exfiltration")
    withheld = not gate["graded"] and gate["oracle_agreement"]["denied_positives"] == 1 and card["grade"] == "?"
    for rel in ("docs/RUN_LOCALLY.md", "docs/CASE_STUDY.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert ("data-exfiltration grade is withheld" in text) is withheld, rel


@pytest.mark.integration
@each_example
@pytest.mark.parametrize("name", ["judge.cassette.json", "result.json"])
def test_verify_fails_on_drift(tmp_path, capsys, ex, name):
    """An edited recording breaks the commitment; an edited result no longer re-derives."""
    ws = tmp_path / "ws"
    shutil.copytree(ex.workspace, ws)
    path = ws / ex.run.relative_to(ex.workspace) / name
    if name == "result.json":
        data = _json(path)
        data["overall_grade"] = "A" if data["overall_grade"] != "A" else "B"
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    code, res = _verify(ws, capsys)
    assert code == 1 and res["ok"] is False and res["reason"]


@pytest.mark.unit
@pytest.mark.parametrize("rel", ["README.md", "docs/RUN_LOCALLY.md", ".github/workflows/ci.yml"])
def test_the_docs_and_ci_run_the_same_verify_commands(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    for ex in EXAMPLES:
        assert ex.verify_command in text, (rel, ex.name)


@pytest.mark.unit
def test_git_keeps_the_recorded_bytes():
    """verify hashes the recordings byte for byte, so a core.autocrlf checkout must not rewrite them."""
    rules = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for ex in EXAMPLES:
        assert f"examples/{ex.name}/** -text" in rules
        assert f"!examples/{ex.name}/.fusion/" in ignore  # the run is committed...
        for stripped in (".secret", "leases.json", "heartbeat.json", ".lock"):
            assert f"examples/{ex.name}/.fusion/**/{stripped}" in ignore  # ...without its run-local state
