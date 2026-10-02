"""Replay recorded attack trajectories through the guardrail (prompt unchanged) and measure the issue
rate drop, scored by the offline detector so it runs without keys.
"""

from __future__ import annotations

import re

from fusion_first.goldset import load_probes
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import GuardConfig
from fusion_first.model.providers import (
    demo_detectors,  # noqa: F401  (registers agentic-check detectors)
)
from fusion_first.model.providers.heuristic import heuristic_criteria
from fusion_first.schemas import BeforeAfterResult, Role, Step, Trajectory
from fusion_first.stats.paired import before_after

# Internal allowlist per check's fictional product (for external-sink detection).
_INTERNAL = {
    "direct_prompt_injection": ["acme.com"],
    "excessive_agency": ["northwind.io"],
    "data_exfiltration": ["vantage.com", "api.internal.vantage.com"],
    "system_prompt_leakage": ["meridianbank.com"],
}

_SECRET_RE = re.compile(r"MB-OVERRIDE-\d{3,}|fr_live_[A-Za-z0-9]{5,}|sk-[A-Za-z0-9]{4,}|sk_live_[A-Za-z0-9]+")


def _extract_secrets(text: str) -> list[str]:
    return sorted(set(_SECRET_RE.findall(text)))


def config_for(check: str, trajectory: Trajectory) -> GuardConfig:
    sysp = trajectory.system_prompt()
    return GuardConfig(
        allowlisted_domains=_INTERNAL.get(check, []),
        secret_values=_extract_secrets(sysp),
        system_prompt=sysp,
        # Least-agency posture: hold consequential actions the user didn't ask for.
        require_authorization=True,
    )


def _user_request(trajectory: Trajectory) -> str:
    return next((s.content for s in trajectory.steps if s.role == Role.USER), "")


def apply_guard_to_trajectory(trajectory: Trajectory, guard: Guardrail) -> Trajectory:
    """The trajectory as the guard would leave it: blocked tool calls dropped, leaks redacted/blocked."""
    user_request = _user_request(trajectory)
    steps: list[Step] = []
    for s in trajectory.steps:
        if s.tool_call is not None:
            if guard.guard_tool_call(s.tool_call.name, s.tool_call.arguments, user_request).blocked:
                continue
            steps.append(s)
            continue
        if s.role == Role.ASSISTANT and s.content:
            guarded = guard.guard_output(s.content)
            steps.append(s.model_copy(update={"content": guarded.content}))
            continue
        steps.append(s)
    return Trajectory(steps=steps)


def run_guard_before_after(check: str, version: str = "v1", seed: int = 42) -> BeforeAfterResult:
    """Baseline attack vs the SAME attack with the guardrail in front (prompt unchanged)."""
    probes = load_probes(check, version)
    baseline_fail: list[bool] = []
    guarded_fail: list[bool] = []
    for p in probes:
        traj = p["baseline"]
        guard = Guardrail(config_for(check, traj))
        guarded = apply_guard_to_trajectory(traj, guard)
        baseline_fail.append(any(heuristic_criteria(traj, check).values()))
        guarded_fail.append(any(heuristic_criteria(guarded, check).values()))
    return before_after(baseline_fail, guarded_fail, seed=seed)
