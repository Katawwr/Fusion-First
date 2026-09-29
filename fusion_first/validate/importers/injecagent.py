"""InjecAgent — indirect prompt injection against tool-using agents (base setting).

Why it is here: it is the external benchmark closest to Fusion's agentic checks. Each case is a user
task that calls a benign tool whose RESPONSE carries an attacker instruction; the agent is compromised
if it then calls one of the attacker's tools. Two kinds:

  * ``dh`` — direct harm (unlock doors, move money): one attacker tool call is the harm.
  * ``ds`` — data stealing: read private data, then exfiltrate it (two attacker tools).

Normalization undoes two upstream encoding quirks so consumers never re-parse strings:
  * ``Tool Parameters`` is a Python-repr string → parsed into a dict with ``ast.literal_eval``
    (literals only — no code runs).
  * ``Tool Response`` is the tool output wrapped in an extra pair of double quotes — usually a valid
    JSON string, but some rows contain unescaped inner quotes. See :func:`decode_tool_response`.

Ids are positional per file (``injecagent:dh:0042``) and pinned by the raw sha256 in SOURCES.yaml.
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
    """Return the text the tool actually returned.

    Upstream stores it wrapped in double quotes. Most rows are a valid JSON string (so escaped inner
    quotes decode correctly); some contain raw inner quotes and are not valid JSON, so we strip the
    wrapper and unescape ``\\"`` by hand. Anything else is returned untouched.
    """
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
    """Normalize ``test_cases_{dh,ds}_base.json`` into rows (``tools.json`` is not needed)."""
    # Imported lazily: the package __init__ imports this module to build SOURCES.
    from fusion_first.validate.importers import existing_files

    by_file = {f"test_cases_{k}_base.json": k for k in KINDS}
    rows: list[dict] = []
    for path in existing_files(raw_dir, list(by_file), NAME):
        kind = by_file[path.name]
        cases = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cases, list):
            raise ValueError(f"{NAME} {path.name}: expected a list of cases")
        for i, case in enumerate(cases):
            where = f"{NAME} {path.name} case {i}"
            missing = [k for k in (*_FIELDS, "Tool Parameters", "Tool Response", "Attacker Tools")
                       if k not in case]
            if missing:
                raise ValueError(f"{where}: missing fields {missing}")
            tools = case["Attacker Tools"]
            if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
                raise ValueError(f"{where}: Attacker Tools must be a list of strings")
            row = {
                "id": f"{NAME}:{kind}:{i:04d}",
                "source": f"external:{NAME}@{path.name}",
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
