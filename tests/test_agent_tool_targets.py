"""A user's own tool-using agent as the tool-loop target: `cmd:` programs and `python:` functions report their tool
calls, and Fusion answers each with a scripted result. Offline: the "agents" here are fixed scripts."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

from fusion_first.attacks.toolsim import ScriptedTurn
from fusion_first.engine.tool_loop import ToolsUnsupported, run_tool_loop
from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.providers._common import agent_tool_calls
from fusion_first.model.providers.command import CommandModelClient, CommandTargetError
from fusion_first.offline import OFFLINE_ENV
from fusion_first.schemas import Role
from fusion_first.targets import FunctionModelClient

TOOLS = [{"type": "function", "function": {"name": "read_inbox", "description": "Read mail", "parameters": {
    "type": "object", "properties": {}}}}]

# An "agent" that reads its inbox once, then answers with what the tool returned.
AGENT = """
import json, sys
req = json.load(sys.stdin)
results = [m for m in req["messages"] if m["role"] == "tool"]
if "tools" not in req:
    print("no tools offered")
elif not results:
    print(json.dumps({"text": "", "tool_calls": [{"name": req["tools"][0]["function"]["name"], "arguments": {"n": 1}}]}))
else:
    print(json.dumps({"text": "The inbox says: " + results[-1]["content"], "tool_calls": []}))
"""


def _cmd(tmp_path, source: str) -> CommandModelClient:
    script = tmp_path / "agent.py"
    script.write_text(source, encoding="utf-8")
    return CommandModelClient(f'"{sys.executable}" "{script}"')


def _loop(client):
    script = [ScriptedTurn(result="2 new messages", tool="read_inbox")]
    return asyncio.run(run_tool_loop(system_prompt="You are an assistant.", user="Check my mail.", tools=TOOLS,
                                     script=script, client=client, model_id=None))


@pytest.mark.unit
def test_agent_tool_calls_accepts_both_shapes_and_reports_a_malformed_call():
    flat = [{"name": "send", "arguments": {"to": "a"}}, {"name": "read"}]
    assert agent_tool_calls(flat) == [{"name": "send", "arguments": {"to": "a"}}, {"name": "read", "arguments": {}}]
    openai = [{"id": "1", "type": "function", "function": {"name": "send", "arguments": '{"to": "a"}'}}]
    assert agent_tool_calls(openai) == [{"name": "send", "arguments": {"to": "a"}}]
    assert agent_tool_calls([]) == []
    for bad in ("send", [{"arguments": {}}], [{"name": "send", "arguments": "not json"}],
                [{"name": "send", "arguments": [1]}], ["send"]):
        with pytest.raises(ValueError):
            agent_tool_calls(bad)


@pytest.mark.integration
def test_a_command_agent_runs_the_tool_loop_and_gets_the_scripted_result(tmp_path, monkeypatch):
    monkeypatch.delenv(OFFLINE_ENV, raising=False)
    result = _loop(_cmd(tmp_path, AGENT))
    assert result.stop == "final" and result.turns == 2
    steps = result.trajectory.steps
    call = next(s for s in steps if s.tool_call)
    assert (call.tool_call.name, call.tool_call.arguments) == ("read_inbox", {"n": 1})
    assert next(s for s in steps if s.tool_result).tool_result.content == "2 new messages"
    assert steps[-1].role == Role.ASSISTANT and steps[-1].content == "The inbox says: 2 new messages"


@pytest.mark.integration
def test_a_command_gets_no_tools_key_unless_tools_are_offered_and_a_plain_reply_ignores_them(tmp_path, monkeypatch):
    monkeypatch.delenv(OFFLINE_ENV, raising=False)
    client = _cmd(tmp_path, AGENT)
    plain = asyncio.run(client.complete(ModelRequest(role=ModelRole.TARGET, system="s",
                                                     messages=[{"role": "user", "content": "hi"}])))
    assert plain.text == "no tools offered" and plain.tool_calls is None
    deaf = _cmd(tmp_path, 'print("I cannot use tools.")')
    with pytest.raises(ToolsUnsupported):
        _loop(deaf)
    # tool_calls in a reply to a request that offered none is not read as calls: the JSON passes through whole
    eager = _cmd(tmp_path, 'import json; print(json.dumps({"verdict": "ok", "tool_calls": []}))')
    out = asyncio.run(eager.complete(ModelRequest(role=ModelRole.JUDGE, system="s",
                                                  messages=[{"role": "user", "content": "hi"}])))
    assert out.tool_calls is None and json.loads(out.text) == {"verdict": "ok", "tool_calls": []}


@pytest.mark.integration
def test_a_malformed_call_from_a_command_is_an_error_not_a_dropped_call(tmp_path, monkeypatch):
    monkeypatch.delenv(OFFLINE_ENV, raising=False)
    broken = _cmd(tmp_path, 'import json; print(json.dumps({"text": "", "tool_calls": [{"arguments": {}}]}))')
    with pytest.raises(CommandTargetError, match="needs a name"):
        _loop(broken)


@pytest.mark.unit
def test_a_python_function_with_a_tools_parameter_runs_the_tool_loop():
    seen = []

    def agent(system, messages, tools):
        seen.append(tools)
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            return {"text": "", "tool_calls": [{"name": "read_inbox", "arguments": {}}]}
        return {"text": f"Done: {results[-1]['content']}", "tool_calls": []}

    result = _loop(FunctionModelClient(agent))
    assert result.stop == "final" and seen == [TOOLS, TOOLS]
    assert result.trajectory.steps[-1].content == "Done: 2 new messages"

    async def async_agent(system, messages, tools=None):
        return {"text": "nothing to do", "tool_calls": []}

    assert _loop(FunctionModelClient(async_agent)).turns == 1


@pytest.mark.unit
def test_a_two_parameter_function_is_unchanged_and_stops_a_tool_loop():
    def bot(system, messages):
        return "hello"

    client = FunctionModelClient(bot)
    out = asyncio.run(client.complete(ModelRequest(role=ModelRole.TARGET, system="s",
                                                   messages=[{"role": "user", "content": "hi"}])))
    assert out.text == "hello" and out.tool_calls is None
    with pytest.raises(ToolsUnsupported):
        _loop(client)
    with pytest.raises(TypeError):
        asyncio.run(FunctionModelClient(lambda s, m: {"text": "x"}).complete(
            ModelRequest(role=ModelRole.TARGET, system="s", messages=[])))
