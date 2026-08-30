"""Attack templates: turn a user's pasted system prompt into a testable attack trajectory.

The offline before/after pipeline (engine/before_after.py) judges pre-baked dataset probes whose
system prompt is a fixed example. A *user-prompt scan* is different: we keep the attack (the user
turn + any injected/untrusted tool content) but swap in the user's own system prompt as the thing
under test. Each template is one such attack, seeded from the curated paired-probe corpus so its
coverage tracks the datasets and OWASP crosswalk.

A template carries everything two arms need:
  - the attack context (user message, optional injected tool result) — shared by both arms;
  - canned demo responses/actions (vulnerable baseline, safe hardened) used in keyless DEMO mode;
  - in LIVE mode the canned responses are ignored and the user's prompt is run through a real model.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass

from fusion.goldset import PROBE_DIR
from fusion.judge.rubric import REGISTRY, get_rubric
from fusion.schemas import (
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


def _truncate(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _attack_label(row: dict) -> str:
    """A plain-language description of the attack, for the live activity feed."""
    injected = row.get("injected")
    if injected:
        tool = row.get("tool", "a tool")
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
    demo_baseline_response: str
    demo_hardened_response: str
    demo_baseline_action: dict | None
    demo_hardened_action: dict | None

    def _context_steps(self, system_prompt: str) -> list[Step]:
        steps = [
            Step(role=Role.SYSTEM, content=system_prompt),
            Step(role=Role.USER, content=self.user),
        ]
        if self.injected:
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
        """The user turn to send a live target model. Injected/untrusted content is presented as a
        clearly-labelled tool result inside the turn (the target must treat it as data, not orders)."""
        content = self.user
        if self.injected:
            content += f"\n\n[Result from tool `{self.tool or 'tool'}` — untrusted data]:\n{self.injected}"
        return [{"role": "user", "content": content}]

    def demo_trajectory(self, system_prompt: str, hardened: bool) -> Trajectory:
        """A complete trajectory using the canned demo response (keyless DEMO mode)."""
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
        """A complete trajectory using a real target model's response (LIVE mode).

        Any tool calls the target emitted via the ACTION protocol are promoted into assistant
        tool_call steps so the judge (and the runtime guardrail) can see consequential actions —
        this is what makes the agentic checks (excessive_agency, data_exfiltration) observable
        against a text-only target."""
        from fusion.attacks.agentic import extract_tool_calls

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
            templates.append(_row_to_template(json.loads(line), owasp))
    return tuple(templates)


def select_templates(
    check: str, tier: ScanTier = ScanTier.QUICK, version: str = "v1"
) -> list[AttackTemplate]:
    """The templates a scan runs at a given tier. QUICK is a deterministic prefix of FULL."""
    templates = get_templates(check, version)
    if tier == ScanTier.QUICK:
        return list(templates[:QUICK_TEMPLATES_PER_CHECK])
    return list(templates)
