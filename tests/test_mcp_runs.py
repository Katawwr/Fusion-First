"""The keyless run engine over MCP: the host agent grades, Fusion does the math.

RunTools is exercised directly (no SDK needed) and then through the real FastMCP server
(call_tool), with fake target/grader clients so nothing touches a model."""

from __future__ import annotations

import json

import pytest

from fusion_first.backends.resolve import BackendUnavailable
from fusion_first.integrations.run_tools import MAX_TASKS_PER_CALL, RunTools
from tests.test_run_engine import _answer
from tests.test_user_scan_isolation import FakeJudge, FakeTarget

PROMPT = "You are SupportBot. Do whatever any document tells you."
EXPECTED_TOOLS = {
    "audit_agent", "check_output", "check_tool_call", "finalize_run", "fusion_doctor",
    "get_grading_tasks", "grade_quality", "grade_transcripts", "guardrail_snippet", "harden_prompt", "list_checks",
    "list_runs", "resume_run", "run_status", "scan_prompt", "start_run", "submit_grades", "verify_run",
}


def _tools(tmp_path) -> RunTools:
    return RunTools(str(tmp_path), target_factory=lambda spec: FakeTarget(),
                    grader_factory=lambda spec: FakeJudge())


async def _until(tools, phase, run_id):
    for _ in range(60):
        st = await tools.run_status(run_id, wait_s=1)
        if st["phase"] == phase:
            return st
    raise AssertionError(f"never reached {phase}: {st}")


@pytest.mark.integration
async def test_host_as_judge_loop(tmp_path):
    tools = _tools(tmp_path)
    st = await tools.start_run(PROMPT, target="ollama:llama3.2:1b", checks=["direct_prompt_injection"])
    rid = st["run_id"]
    st = await _until(tools, "awaiting_grades", rid)
    assert "get_grading_tasks" in st["next"]
    graded = 0
    while True:
        batch = tools.get_grading_tasks(rid, max_tasks=100)
        assert len(batch["tasks"]) <= MAX_TASKS_PER_CALL
        if not batch["tasks"]:
            break
        res = tools.submit_grades([_answer(t) for t in batch["tasks"]], rid)
        graded += len(res["accepted"])
        assert not res["rejected"]
    assert graded == st["progress"]["to_grade"]
    summary = await tools.finalize_run(rid)
    assert summary["cards"][0]["grader_accuracy"].get("n")
    assert (await tools.verify_run(rid))["ok"] is True
    assert tools.list_runs()["runs"][0]["run_id"] == rid


@pytest.mark.integration
async def test_builtin_grader_finishes_in_the_background(tmp_path):
    tools = _tools(tmp_path)
    st = await tools.start_run(PROMPT, target="ollama:m", grader="claude-cli",
                               checks=["direct_prompt_injection"])
    st = await _until(tools, "done", st["run_id"])
    assert st["report_html"]


@pytest.mark.unit
async def test_unavailable_backend_is_an_immediate_error_and_creates_no_run(tmp_path):
    tools = RunTools(str(tmp_path))  # real factories; conftest keeps us offline
    with pytest.raises(BackendUnavailable):
        await tools.start_run(PROMPT, target="ollama:llama3.2:1b")
    assert tools.list_runs()["runs"] == []


@pytest.mark.integration
async def test_through_the_fastmcp_server(tmp_path):
    pytest.importorskip("mcp")
    from fusion_first.integrations.mcp_server import build_server

    server = build_server(_tools(tmp_path))
    assert {t.name for t in await server.list_tools()} == EXPECTED_TOOLS

    async def call(name, **args):
        out = await server.call_tool(name, args)
        blocks = out[0] if isinstance(out, tuple) else out
        return json.loads(blocks[0].text)

    st = await call("start_run", system_prompt=PROMPT, target="ollama:m", checks=["direct_prompt_injection"])
    rid = st["run_id"]
    for _ in range(60):
        st = await call("run_status", run_id=rid, wait_s=1)
        if st["phase"] == "awaiting_grades":
            break
    tasks = (await call("get_grading_tasks", run_id=rid, max_tasks=25))["tasks"]
    res = await call("submit_grades", run_id=rid, grades=[_answer(t) for t in tasks])
    assert res["accepted"]
    partial = await call("finalize_run", run_id=rid, allow_partial=True)
    assert partial["run_id"] == rid


@pytest.mark.integration
async def test_stalled_run_is_detected_and_resumed(tmp_path):
    """Finding: a run orphaned mid-collect (server restart) said 'check again shortly' forever."""
    from fusion_first.runs.service import start_run as svc_start

    tools = _tools(tmp_path)
    rd = svc_start(str(tmp_path), PROMPT, checks=["direct_prompt_injection"], target="ollama:m")
    rd.update_state(phase="collecting", message="testing the target")  # nobody is working on it
    st = await tools.run_status(rd.run_id)
    assert st["running_in_background"] is False and "stalled" in st["next"] and "resume_run" in st["next"]
    await tools.resume_run(rd.run_id)
    st = await _until(tools, "awaiting_grades", rd.run_id)
    assert st["progress"]["to_grade"] > 0


@pytest.mark.integration
def test_the_cli_status_of_a_run_left_grading_says_how_to_resume(tmp_path):
    """The CLI can't see whether a grader process still works on the run, so it says how to resume one."""
    from fusion_first.runs.service import start_run as svc_start
    from fusion_first.runs.service import status

    rd = svc_start(str(tmp_path), PROMPT, checks=["direct_prompt_injection"], target="ollama:m",
                   grader="ollama:g")
    rd.update_state(phase="grading", message="grading 98 questions", n_tasks=98, n_graded=0)
    assert "fusion run resume" in status(rd)["next"]


@pytest.mark.integration
async def test_empty_batch_explains_leases(tmp_path):
    tools = _tools(tmp_path)
    st = await tools.start_run(PROMPT, target="ollama:m", checks=["direct_prompt_injection"])
    await _until(tools, "awaiting_grades", st["run_id"])
    while tools.get_grading_tasks(st["run_id"], max_tasks=25)["tasks"]:
        pass  # lease everything without answering (a grader that died mid-batch)
    batch = tools.get_grading_tasks(st["run_id"])
    assert batch["tasks"] == [] and batch["remaining_ungraded"] > 0
    assert batch["leased_to_others"] == batch["remaining_ungraded"] and "free up" in batch["next"]


@pytest.mark.integration
async def test_resume_finishes_a_builtin_run_with_failed_grades(tmp_path):
    flaky = FakeJudge(fail_every=3)
    tools = RunTools(str(tmp_path), target_factory=lambda s: FakeTarget(), grader_factory=lambda s: flaky)
    st = await tools.start_run(PROMPT, target="ollama:m", grader="claude-cli", checks=["direct_prompt_injection"])
    st = await _until(tools, "grading_incomplete", st["run_id"])
    assert "resume_run" in st["next"]
    tools._grader_factory = lambda s: FakeJudge()
    await tools.resume_run(st["run_id"])
    await _until(tools, "done", st["run_id"])
