"""Scripted tool results for the tool loop: a pure function of (tool, arguments, turn, script).

Nothing is executed. A v2 probe row's `turns` script the result each tool call receives; a call no
scripted turn matches gets a deterministic default result, so record/replay keys stay stable.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ScriptedTurn:
    result: str
    turn: int | None = None  # 1-based assistant turn, None = any
    tool: str | None = None  # tool name, None or "*" = any
    injected: bool = False


@dataclass(frozen=True)
class SimResult:
    content: str
    injected: bool
    scripted: bool  # False when the default result was used


def default_result(tool: str, arguments: dict) -> str:
    """The result of an unscripted call: deterministic, independent of the arguments."""
    return json.dumps({"status": "ok", "tool": tool})


def _matches(entry: ScriptedTurn, tool: str, turn: int) -> bool:
    return entry.turn in (None, turn) and entry.tool in (None, "*", tool)


def simulate(tool: str, arguments: dict, turn: int, script: Sequence[ScriptedTurn]) -> SimResult:
    """The first scripted turn matching `turn` and `tool` wins; otherwise the default result."""
    for entry in script:
        if _matches(entry, tool, turn):
            return SimResult(entry.result, entry.injected, True)
    return SimResult(default_result(tool, arguments), False, False)


def parse_script(rows: Iterable[dict]) -> tuple[ScriptedTurn, ...]:
    """A v2 row's `turns` as ScriptedTurns; a malformed row raises ValueError naming the bad field."""
    out: list[ScriptedTurn] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"turns[{i}]: must be an object, got {type(row).__name__}")
        result = row.get("result")
        if not isinstance(result, str):
            raise ValueError(f"turns[{i}].result: must be a string")
        turn = row.get("turn")
        if turn is not None and (type(turn) is not int or turn < 1):
            raise ValueError(f"turns[{i}].turn: must be an integer >= 1 or null, got {turn!r}")
        tool = row.get("tool")
        if tool is not None and not isinstance(tool, str):
            raise ValueError(f"turns[{i}].tool: must be a string or null, got {tool!r}")
        injected = row.get("injected", False)
        if not isinstance(injected, bool):
            raise ValueError(f"turns[{i}].injected: must be a boolean, got {injected!r}")
        out.append(ScriptedTurn(result=result, turn=turn, tool=tool, injected=injected))
    return tuple(out)
