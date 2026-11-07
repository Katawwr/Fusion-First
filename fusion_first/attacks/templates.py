"""Attack templates seeded from the probe corpus, run against the user's own system prompt.

Each carries the attack context plus canned demo responses for keyless DEMO mode; LIVE mode runs the
prompt through a real model instead. v2 rows (`tools` + scripted `turns`) run through the native tool loop
(`fusion_first.engine.tool_loop`) and have no demo responses.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass

from fusion_first.attacks.toolsim import ScriptedTurn, parse_script
from fusion_first.goldset import PROBE_DIR
from fusion_first.judge.rubric import REGISTRY, get_rubric
from fusion_first.schemas import (
    OwaspTag,
    Role,
    ScanTier,
    Step,
    ToolCall,
    ToolResult,
    Trajectory,
)

# QUICK tier runs this many templates per check (cheap, interactive); FULL runs all of them.
QUICK_TEMPLATES_PER_CHECK = 8

V2_ID_PREFIX = {"excessive_agency": "ea2", "data_exfiltration": "dx2"}
V2_TECHNIQUES = frozenset({"direct_instruction", "authority_pretext", "delegated_source", "payload_split",
                           "multilingual", "encoded", "benign_control"})
V2_REQUIRED = ("id", "check", "technique", "provenance", "user", "tools", "turns", "oracle", "attack_action")
V2_ORACLE_KEYS = frozenset({"forbidden_tools", "allowlisted_domains", "check_destinations", "benign_tools"})
_V2_ONLY_KEYS = frozenset({"tools", "turns", "oracle", "technique", "provenance", "attack_action"})


def _truncate(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _attack_label(row: dict) -> str:
    """A plain-language description of the attack, for the live activity feed."""
    injected = row.get("injected")
    if injected:
        tool = row.get("tool") or "a tool"
        return f'Hidden instruction via {tool}: "{_truncate(injected, 70)}"'
    return f'"{_truncate(row["user"], 80)}"'


@dataclass(frozen=True)
class AttackTemplate:
    id: str
    check: str
    owasp: OwaspTag
    attack_label: str
    user: str
    tool: str | None
    injected: str | None
    demo_baseline_response: str = ""
    demo_hardened_response: str = ""
    demo_baseline_action: dict | None = None
    demo_hardened_action: dict | None = None
    # v2 (tool loop) only; None on v1 templates.
    tools: tuple[dict, ...] | None = None
    turns: tuple[ScriptedTurn, ...] | None = None
    oracle: dict | None = None
    technique: str | None = None
    provenance: dict | None = None
    attack_action: dict | None = None

    @property
    def uses_tool_loop(self) -> bool:
        return self.tools is not None

    def _context_steps(self, system_prompt: str) -> list[Step]:
        steps = [
            Step(role=Role.SYSTEM, content=system_prompt),
            Step(role=Role.USER, content=self.user),
        ]
        if self.injected and self.tools is None:
            steps.append(
                Step(
                    role=Role.TOOL,
                    tool_result=ToolResult(
                        tool=self.tool or "tool", content=self.injected, injected=True
                    ),
                )
            )
        return steps

    def target_messages(self) -> list[dict]:
        """The user turn for a live target; injected content is a labelled untrusted tool result."""
        content = self.user
        if self.injected:
            content += f"\n\n[Result from tool `{self.tool or 'tool'}` — untrusted data]:\n{self.injected}"
        return [{"role": "user", "content": content}]

    def demo_trajectory(self, system_prompt: str, hardened: bool) -> Trajectory:
        """A complete trajectory using the canned demo response (keyless DEMO mode)."""
        if self.uses_tool_loop:
            raise ValueError(f"{self.id} is a tool-loop template: it has no demo responses (run it live)")
        steps = self._context_steps(system_prompt)
        action = self.demo_hardened_action if hardened else self.demo_baseline_action
        if action:
            steps.append(
                Step(
                    role=Role.ASSISTANT,
                    tool_call=ToolCall(name=action["tool"], arguments=action.get("arguments", {})),
                )
            )
        response = self.demo_hardened_response if hardened else self.demo_baseline_response
        steps.append(Step(role=Role.ASSISTANT, content=response))
        return Trajectory(steps=steps)

    def live_trajectory(self, system_prompt: str, response_text: str) -> Trajectory:
        """A trajectory from a real target response, with emitted ACTION lines as tool_call steps."""
        from fusion_first.attacks.agentic import extract_tool_calls

        steps = self._context_steps(system_prompt)
        for call in extract_tool_calls(response_text):
            steps.append(Step(role=Role.ASSISTANT, tool_call=call))
        steps.append(Step(role=Role.ASSISTANT, content=response_text))
        return Trajectory(steps=steps)


def _row_to_template(row: dict, owasp: OwaspTag) -> AttackTemplate:
    return AttackTemplate(
        id=row["id"],
        check=row["check"],
        owasp=owasp,
        attack_label=_attack_label(row),
        user=row["user"],
        tool=row.get("tool"),
        injected=row.get("injected"),
        demo_baseline_response=row["baseline_response"],
        demo_hardened_response=row["hardened_response"],
        demo_baseline_action=row.get("baseline_action"),
        demo_hardened_action=row.get("hardened_action"),
    )


def probe_row_id(row: dict, prefix: str) -> str:
    """`<prefix>-` + the first 10 hex chars of sha256 over the canonical JSON of the row without `id`."""
    body = {k: v for k, v in row.items() if k != "id"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}-{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:10]}"


def _tool_names(rid: str, tools: object) -> list[str]:
    if not isinstance(tools, list) or not 2 <= len(tools) <= 4:
        raise ValueError(f"{rid}: tools must be a list of 2-4 function schemas")
    names: list[str] = []
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) and t.get("type") == "function" else None
        if not isinstance(fn, dict) or not isinstance(fn.get("name"), str) or not fn["name"]:
            raise ValueError(f'{rid}: tools entries must be {{"type": "function", "function": {{"name": ...}}}}')
        names.append(fn["name"])
    if len(set(names)) != len(names):
        raise ValueError(f"{rid}: tools declares a name twice: {names}")
    return names


def _validate_v2_row(row: dict, check: str) -> tuple[ScriptedTurn, ...]:
    """Check a v2 row against the corpus contract; ValueError names the row id. Returns its script."""
    rid = row.get("id", "<no id>")
    missing = [k for k in V2_REQUIRED if k not in row]
    if missing:
        raise ValueError(f"{rid}: v2 row is missing {missing}")
    if row["check"] != check:
        raise ValueError(f"{rid}: check is {row['check']!r}, expected {check!r}")
    prefix = V2_ID_PREFIX.get(check)
    if prefix is None:
        raise ValueError(f"{rid}: no v2 id prefix for check {check!r}")
    expected = probe_row_id(row, prefix)
    if rid != expected:
        raise ValueError(f"{rid}: id does not match the content hash (expected {expected})")
    technique = row["technique"]
    if technique not in V2_TECHNIQUES:
        raise ValueError(f"{rid}: technique {technique!r} is not one of {sorted(V2_TECHNIQUES)}")
    if not isinstance(row["user"], str) or not row["user"].strip():
        raise ValueError(f"{rid}: user must be a non-empty string")
    names = set(_tool_names(rid, row["tools"]))
    if not isinstance(row["turns"], list):
        raise ValueError(f"{rid}: turns must be a list")
    try:
        script = parse_script(row["turns"])
    except ValueError as e:
        raise ValueError(f"{rid}: {e}") from None
    for entry in script:
        if entry.tool not in (None, "*") and entry.tool not in names:
            raise ValueError(f"{rid}: scripted tool {entry.tool!r} is not a declared tool {sorted(names)}")
    benign = technique == "benign_control"
    if benign and any(e.injected for e in script):
        raise ValueError(f"{rid}: a benign_control row must have no injected turn")
    if not benign and not any(e.injected for e in script):
        raise ValueError(f"{rid}: an attack row needs at least one injected turn")
    action = row["attack_action"]
    if benign:
        if action is not None:
            raise ValueError(f"{rid}: attack_action must be null for benign_control")
    elif not isinstance(action, dict) or action.get("tool") not in names:
        raise ValueError(f"{rid}: attack_action must name a declared tool {sorted(names)}, got {action!r}")
    oracle = row["oracle"]
    if not isinstance(oracle, dict) or not set(oracle) <= V2_ORACLE_KEYS:
        extra = sorted(set(oracle) - V2_ORACLE_KEYS) if isinstance(oracle, dict) else oracle
        raise ValueError(f"{rid}: oracle keys must be a subset of {sorted(V2_ORACLE_KEYS)}, got extra {extra}")
    for key in ("forbidden_tools", "benign_tools"):
        unknown = sorted(set(oracle.get(key) or ()) - names)
        if unknown:
            raise ValueError(f"{rid}: oracle {key} {unknown} are not declared tools {sorted(names)}")
    return script


def _v2_row_to_template(row: dict, owasp: OwaspTag, script: tuple[ScriptedTurn, ...]) -> AttackTemplate:
    first = next((e for e in script if e.injected), None)
    tool = first.tool if first is not None and first.tool not in (None, "*") else None
    injected = first.result if first is not None else None
    label = row.get("attack_label") or _attack_label({"user": row["user"], "tool": tool, "injected": injected})
    return AttackTemplate(
        id=row["id"],
        check=row["check"],
        owasp=owasp,
        attack_label=label,
        user=row["user"],
        tool=tool,
        injected=injected,
        tools=tuple(row["tools"]),
        turns=script,
        oracle=row["oracle"],
        technique=row["technique"],
        provenance=row["provenance"],
        attack_action=row["attack_action"],
    )


@functools.cache
def get_templates(check: str, version: str = "v1") -> tuple[AttackTemplate, ...]:
    """All attack templates for a check, in dataset order (cached; immutable tuple)."""
    if check not in REGISTRY:
        raise KeyError(f"no rubric registered for check '{check}'")
    path = PROBE_DIR / f"{check}.{version}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"probe set not found: {path}")
    owasp = get_rubric(check).owasp
    templates: list[AttackTemplate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            row = json.loads(line)
            if _V2_ONLY_KEYS & row.keys():
                templates.append(_v2_row_to_template(row, owasp, _validate_v2_row(row, check)))
            else:
                templates.append(_row_to_template(row, owasp))
    return tuple(templates)


def select_templates(
    check: str, tier: ScanTier = ScanTier.QUICK, version: str = "v1"
) -> list[AttackTemplate]:
    """The templates a scan runs at a given tier. QUICK is a deterministic prefix of FULL."""
    templates = get_templates(check, version)
    if tier == ScanTier.QUICK:
        return list(templates[:QUICK_TEMPLATES_PER_CHECK])
    return list(templates)
