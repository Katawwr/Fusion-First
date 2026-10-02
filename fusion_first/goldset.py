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


def _row_to_case(row: dict) -> JudgeCase:
    steps: list[Step] = [
        Step(role=Role.SYSTEM, content=row["system"]),
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
    if row.get("action"):
        act = row["action"]
        steps.append(
            Step(
                role=Role.ASSISTANT,
                tool_call=ToolCall(name=act["tool"], arguments=act.get("arguments", {})),
            )
        )
    steps.append(Step(role=Role.ASSISTANT, content=row["response"]))
    o = row["oracle"]
    return JudgeCase(
        id=row["id"],
        check=row["check"],
        split=row.get("split", "dev"),
        trajectory=Trajectory(steps=steps),
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
