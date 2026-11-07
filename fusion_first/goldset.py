"""Load the jsonl gold set and paired probes; each compact row expands into a trajectory."""

from __future__ import annotations

import json

from fusion_first._data import data_root
from fusion_first.schemas import (
    JudgeCase,
    Label,
    OwaspTag,
    Role,
    Severity,
    Step,
    ToolCall,
    ToolResult,
    Trajectory,
)

GOLD_DIR = data_root() / "datasets" / "gold"


def _authored_step(s: dict) -> Step:
    """One gold v2 `steps` entry: an assistant tool call, an assistant prose turn, or a tool result."""
    if not isinstance(s, dict):
        raise ValueError(f"a gold step must be an object, got {s!r}")
    role = s.get("role")
    if role == "assistant" and "tool_call" in s:
        if "content" in s:
            raise ValueError("an assistant step holds a tool_call or content, not both")
        call = s["tool_call"]
        if not isinstance(call, dict) or not isinstance(call.get("name"), str):
            raise ValueError(f"a tool_call needs a string name: {call!r}")
        return Step(role=Role.ASSISTANT, tool_call=ToolCall(name=call["name"], arguments=call.get("arguments", {})))
    if role == "assistant":
        if not isinstance(s.get("content"), str):
            raise ValueError("an assistant step needs a tool_call or string content")
        return Step(role=Role.ASSISTANT, content=s["content"])
    if role == "tool":
        injected = s.get("injected", False)
        if not isinstance(s.get("tool"), str) or not isinstance(s.get("content"), str):
            raise ValueError("a tool step needs string 'tool' and 'content'")
        if not isinstance(injected, bool):
            raise ValueError(f"'injected' must be a boolean, got {injected!r}")
        return Step(role=Role.TOOL, tool_result=ToolResult(tool=s["tool"], content=s["content"], injected=injected))
    raise ValueError(f"a gold step's role must be 'assistant' or 'tool', got {role!r}")


def gold_trajectory(row: dict) -> Trajectory:
    """The trajectory a gold row describes. v2 rows list `steps` (tool calls, tool results, prose, in order);
    v1 rows carry at most one `injected` tool result and one `action`. `response` is the final assistant step."""
    steps: list[Step] = [
        Step(role=Role.SYSTEM, content=row["system"]),
        Step(role=Role.USER, content=row["user"]),
    ]
    if "steps" in row:
        if row.get("injected") or row.get("action") or not isinstance(row["steps"], list):
            raise ValueError("a gold row lists `steps` (v2) or `injected`/`action` (v1), not both")
        steps.extend(_authored_step(s) for s in row["steps"])
    else:
        if row.get("injected"):
            steps.append(
                Step(
                    role=Role.TOOL,
                    tool_result=ToolResult(
                        tool=row.get("tool", "tool"), content=row["injected"], injected=True
                    ),
                )
            )
        if row.get("action"):
            act = row["action"]
            steps.append(
                Step(
                    role=Role.ASSISTANT,
                    tool_call=ToolCall(name=act["tool"], arguments=act.get("arguments", {})),
                )
            )
    steps.append(Step(role=Role.ASSISTANT, content=row["response"]))
    return Trajectory(steps=steps)


def _row_to_case(row: dict) -> JudgeCase:
    o = row["oracle"]
    return JudgeCase(
        id=row["id"],
        check=row["check"],
        split=row.get("split", "dev"),
        trajectory=gold_trajectory(row),
        oracle=Label(
            is_issue=o["is_issue"],
            severity=Severity(o.get("severity", "NONE")),
            issue_type=o.get("issue_type"),
            source=o.get("source", "oracle:handcrafted"),
        ),
        owasp=OwaspTag(**row.get("owasp", {"llm": "LLM01", "asi": "ASI01"})),
    )


def load_gold(check: str, version: str = "v1") -> list[JudgeCase]:
    path = GOLD_DIR / f"{check}.{version}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"gold set not found: {path}")
    cases: list[JudgeCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            cases.append(_row_to_case(json.loads(line)))
    return cases


def gold_version_hash(check: str, version: str = "v1") -> str:
    import hashlib

    path = GOLD_DIR / f"{check}.{version}.jsonl"
    # Line-ending independent, so a Windows (autocrlf) checkout hashes like a Linux one.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:12]


PROBE_DIR = data_root() / "datasets" / "probes"


def _probe_trajectory(row: dict, response_key: str, action_key: str | None = None) -> Trajectory:
    steps: list[Step] = [
        Step(role=Role.SYSTEM, content=row.get("system", "You are the ACME support assistant.")),
        Step(role=Role.USER, content=row["user"]),
    ]
    if row.get("injected"):
        steps.append(
            Step(
                role=Role.TOOL,
                tool_result=ToolResult(
                    tool=row.get("tool", "tool"), content=row["injected"], injected=True
                ),
            )
        )
    if action_key and row.get(action_key):
        act = row[action_key]
        steps.append(
            Step(
                role=Role.ASSISTANT,
                tool_call=ToolCall(name=act["tool"], arguments=act.get("arguments", {})),
            )
        )
    steps.append(Step(role=Role.ASSISTANT, content=row[response_key]))
    return Trajectory(steps=steps)


def load_probes(check: str, version: str = "v1") -> list[dict]:
    """Paired probes as {id, baseline: Trajectory, hardened: Trajectory}."""
    path = PROBE_DIR / f"{check}.{version}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"probe set not found: {path}")
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            row = json.loads(line)
            out.append(
                {
                    "id": row["id"],
                    "baseline": _probe_trajectory(row, "baseline_response", "baseline_action"),
                    "hardened": _probe_trajectory(row, "hardened_response", "hardened_action"),
                }
            )
    return out
