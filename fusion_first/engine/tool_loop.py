"""The bounded tool loop: a target answers with native tool calls, scripted tool results go back
(`fusion_first.attacks.toolsim`, nothing executed), for at most `MAX_ASSISTANT_TURNS` assistant turns.

Contract with the providers (`ModelResponse.tool_calls`): when tools are offered, a tool-capable backend
(Ollama, OpenAI-compatible) returns a list, `[]` when the model made no call; the loop treats `[]` as the
final turn (`stop="final"`). `None` means the backend ignores tools (claude-cli, cmd:, python:, host): the
loop raises `ToolsUnsupported`, which is not isolatable, since every case of the run would fail the same way.

Messages use one provider-agnostic shape, built deterministically so record/replay keys are stable:
assistant tool calls carry `id = call_<turn>_<i>` and dict `arguments`; tool results carry `tool_call_id`
and `name`. The OpenAI-compatible provider JSON-encodes the arguments on the wire; the Ollama provider
needs no change (it accepts dict arguments and ignores the extra `id`, `type` and `tool_call_id` keys).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from fusion_first.attacks.toolsim import ScriptedTurn, simulate
from fusion_first.errors import FatalRunError, FusionProviderError
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse, ModelRole
from fusion_first.schemas import Role, Step, ToolCall, ToolResult, Trajectory

MAX_ASSISTANT_TURNS = 4


class ToolsUnsupported(FusionProviderError, FatalRunError):
    """The target backend returned no tool_calls field for a request that offered tools."""


@dataclass
class ToolLoopResult:
    trajectory: Trajectory
    responses: list[ModelResponse]  # one per assistant turn, for accounting
    turns: int
    stop: str  # "final" | "max_turns"


def _arguments(call: dict) -> dict:
    """The call's arguments with keys sorted at every level (a cassette stores responses key-sorted, so a
    replayed trajectory would otherwise differ from the recorded one); undecodable provider text is kept
    as {"raw": <text>}."""
    if "arguments_raw" in call:
        return {"raw": call["arguments_raw"]}
    args = call.get("arguments")
    return json.loads(json.dumps(args, sort_keys=True)) if isinstance(args, dict) else {}


async def run_tool_loop(
    *,
    system_prompt: str,
    user: str,
    tools: Sequence[dict],
    script: Sequence[ScriptedTurn],
    client: ModelClient,
    model_id: str | None,
    max_turns: int = MAX_ASSISTANT_TURNS,
    max_tokens: int = 800,
) -> ToolLoopResult:
    messages: list[dict] = [{"role": "user", "content": user}]
    steps = [Step(role=Role.SYSTEM, content=system_prompt), Step(role=Role.USER, content=user)]
    responses: list[ModelResponse] = []
    for turn in range(1, max_turns + 1):
        resp = await client.complete(ModelRequest(
            role=ModelRole.TARGET, system=system_prompt, messages=list(messages), tools=list(tools),
            max_tokens=max_tokens, model_id=model_id,
        ))
        responses.append(resp)
        if resp.tool_calls is None:
            raise ToolsUnsupported(
                f"the target backend returned no tool_calls field for a request that offered tools "
                f"(model {resp.model!r}); use a tool-capable backend (ollama:, openai-compat:)")
        calls = [(c["name"], _arguments(c)) for c in resp.tool_calls]
        for name, args in calls:
            steps.append(Step(role=Role.ASSISTANT, tool_call=ToolCall(name=name, arguments=args)))
        if resp.text.strip():
            steps.append(Step(role=Role.ASSISTANT, content=resp.text))
        if not calls:
            return ToolLoopResult(Trajectory(steps=steps), responses, turn, "final")
        ids = [f"call_{turn}_{i}" for i in range(len(calls))]
        messages.append({"role": "assistant", "content": resp.text, "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}
            for cid, (name, args) in zip(ids, calls, strict=True)]})
        for cid, (name, args) in zip(ids, calls, strict=True):
            sim = simulate(name, args, turn, script)
            steps.append(Step(role=Role.TOOL, tool_result=ToolResult(tool=name, content=sim.content,
                                                                     injected=sim.injected)))
            messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": sim.content})
    return ToolLoopResult(Trajectory(steps=steps), responses, max_turns, "max_turns")
