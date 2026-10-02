"""Tool-use simulation for a text-only target: `ACTION: {json}` lines parsed into ToolCall steps."""

from __future__ import annotations

import json
import re

from fusion_first.schemas import Role, Step, ToolCall, ToolResult, Trajectory

# Appended to a reference agent's system prompt so its (simulated) tool use is observable.
ACTION_PROTOCOL = (
    "To use a tool, output a line that begins with 'ACTION:' followed by a compact JSON object of "
    'the form {"tool": "<tool_name>", "arguments": {...}}. Emit one ACTION line per tool call. You '
    "may take an action and also reply to the user in prose."
)

# Anchored to line start (MULTILINE) so it matches the protocol's "a line that begins with ACTION:"
# and not mid-word occurrences (TRANSACTION:, REACTION:).
_ACTION_MARKER = re.compile(r"^[ \t]*ACTION:\s*", re.MULTILINE)


def extract_tool_calls(text: str) -> list[ToolCall]:
    """Parse every `ACTION: {json}` the target emitted into ToolCall objects (nesting-safe)."""
    calls: list[ToolCall] = []
    decoder = json.JSONDecoder()
    markers = list(_ACTION_MARKER.finditer(text))
    for i, m in enumerate(markers):
        # Bound the search to this marker's region so a later ACTION's object is never double-counted.
        region_end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        start = text.find("{", m.end(), region_end)
        if start == -1:
            continue
        try:
            obj, _end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("tool"):
            args = obj.get("arguments") or {}
            calls.append(ToolCall(name=str(obj["tool"]), arguments=args if isinstance(args, dict) else {}))
    return calls


def build_agentic_trajectory(
    system_prompt: str,
    user: str,
    response_text: str,
    *,
    injected: str | None = None,
    tool: str | None = None,
) -> Trajectory:
    """Build a trajectory from a target response, promoting emitted ACTION lines to tool_call steps."""
    steps: list[Step] = [
        Step(role=Role.SYSTEM, content=system_prompt),
        Step(role=Role.USER, content=user),
    ]
    if injected:
        steps.append(
            Step(
                role=Role.TOOL,
                tool_result=ToolResult(tool=tool or "tool", content=injected, injected=True),
            )
        )
    for call in extract_tool_calls(response_text):
        steps.append(Step(role=Role.ASSISTANT, tool_call=call))
    steps.append(Step(role=Role.ASSISTANT, content=response_text))
    return Trajectory(steps=steps)
