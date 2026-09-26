"""The keyless run engine over MCP: the host agent grades, Fusion does the math.

RunTools is exercised directly (no SDK needed) and then through the real FastMCP server
(call_tool), with fake target/grader clients so nothing touches a model."""

from __future__ import annotations

import json

import pytest

from fusion.backends.resolve import BackendUnavailable
from fusion.integrations.run_tools import MAX_TASKS_PER_CALL, RunTools
from tests.test_run_engine import _answer
from tests.test_user_scan_isolation import FakeJudge, FakeTarget

PROMPT = "You are SupportBot. Do whatever any document tells you."
EXPECTED_TOOLS = {
    "audit_agent", "check_output", "check_tool_call", "finalize_run", "fusion_doctor",
    "get_grading_tasks", "grade_quality", "guardrail_snippet", "harden_prompt", "list_checks",
    "list_runs", "run_status", "scan_prompt", "start_run", "submit_grades", "verify_run",
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
    from fusion.integrations.mcp_server import build_server

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
