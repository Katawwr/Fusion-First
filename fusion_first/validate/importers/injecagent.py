"""InjecAgent: indirect prompt injection against tool-using agents (base setting).

Kinds: ``dh`` direct harm (one attacker tool call), ``ds`` data stealing (read, then exfiltrate).
``Tool Parameters`` (a Python repr) is parsed with ``ast.literal_eval``; ``Tool Response`` is unwrapped
by :func:`decode_tool_response`.
"""

from __future__ import annotations

import ast
import json
import pathlib

NAME = "injecagent"
URL = "https://github.com/uiuc-kang-lab/InjecAgent"
LICENSE = "MIT"
NOTE = "Base setting only. kind dh = direct harm, ds = data stealing (read then exfiltrate)."
KINDS = ("dh", "ds")
SETTINGS = ("base", "enhanced")  # upstream's two files per kind; `injecagent_enhanced` imports the second

_FIELDS = {
    "User Instruction": "user_instruction",
    "User Tool": "user_tool",
    "Tool Response Template": "tool_response_template",
    "Attacker Instruction": "attacker_instruction",
    "Expected Achievements": "expected_achievements",
    "Attack Type": "attack_type",
    "Thought": "thought",
}


def decode_tool_response(raw: str) -> str:
    """The tool's text, unwrapped from upstream's double quotes (JSON-decoded, or stripped by hand
    when raw inner quotes make it invalid JSON)."""
    try:
        value = json.loads(raw)
    except ValueError:
        value = None
    if isinstance(value, str):
        return value
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"')
    return raw


def _parse_parameters(raw: object, where: str) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise ValueError(f"{where}: Tool Parameters must be a string, got {raw!r}")
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError) as exc:
        raise ValueError(f"{where}: unparseable Tool Parameters {raw[:80]!r}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{where}: Tool Parameters is not a mapping: {raw[:80]!r}")
    return value


def load_injecagent(raw_dir: pathlib.Path) -> list[dict]:
    return load_cases(raw_dir)


def load_cases(raw_dir: pathlib.Path, *, name: str = NAME, setting: str = "base") -> list[dict]:
    """One row per case of an upstream setting (`test_cases_<kind>_<setting>.json`), ids `<name>:<kind>:<index>`."""
    # Lazy: the package __init__ imports this module.
    from fusion_first.validate.importers import existing_files

    if setting not in SETTINGS:
        raise ValueError(f"unknown InjecAgent setting {setting!r}: one of {', '.join(SETTINGS)}")
    by_file = {f"test_cases_{k}_{setting}.json": k for k in KINDS}
    rows: list[dict] = []
    for path in existing_files(raw_dir, list(by_file), name):
        kind = by_file[path.name]
        cases = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cases, list):
            raise ValueError(f"{name} {path.name}: expected a list of cases")
        for i, case in enumerate(cases):
            where = f"{name} {path.name} case {i}"
            missing = [k for k in (*_FIELDS, "Tool Parameters", "Tool Response", "Attacker Tools")
                       if k not in case]
            if missing:
                raise ValueError(f"{where}: missing fields {missing}")
            tools = case["Attacker Tools"]
            if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
                raise ValueError(f"{where}: Attacker Tools must be a list of strings")
            row = {
                "id": f"{name}:{kind}:{i:04d}",
                "source": f"external:{name}@{path.name}",
                "license": LICENSE,
                "kind": kind,
                "attacker_tools": list(tools),
                "tool_parameters": _parse_parameters(case["Tool Parameters"], where),
                "tool_response": decode_tool_response(str(case["Tool Response"])),
                # Upstream spells the key "Modifed": whether the authors hand-edited the case.
                "modified": bool(case.get("Modifed", 0)),
            }
            for src, dst in _FIELDS.items():
                if not isinstance(case[src], str):
                    raise ValueError(f"{where}: {src} must be a string")
                row[dst] = case[src]
            rows.append(row)
    return rows
