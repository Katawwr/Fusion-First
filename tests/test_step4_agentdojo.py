"""Step 4 (evals/validation/v1/PREREG_step4_agentdojo.md): the registered decision rules, on synthetic records."""

from __future__ import annotations

import pathlib
import runpy

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
S4 = runpy.run_path(str(ROOT / "scripts/step4_agentdojo.py"), run_name="step4")


def _ep(suite, user, inj, outcomes):
    """outcomes: {arm: (utility, security)}"""
    return [{"suite": suite, "user_task": user, "injection_task": inj, "arm": arm, "utility": u, "security": s}
            for arm, (u, s) in outcomes.items()]


def _benign(n_done_both, n_lost, n_none=0):
    rows = []
    for i in range(n_done_both):
        rows += _ep("workspace", f"u{i}", None, {"none": (True, None), "v2": (True, None), "v3": (True, None)})
    for i in range(n_lost):
        rows += _ep("banking", f"l{i}", None, {"none": (True, None), "v2": (False, None), "v3": (False, None)})
    for i in range(n_none):
        rows += _ep("slack", f"n{i}", None, {"none": (False, None), "v2": (False, None), "v3": (False, None)})
    return rows


@pytest.mark.unit
def test_cost_within_margin_when_the_guard_breaks_no_task():
    s = S4["score_rows"](_benign(25, 0, 75))
    assert s["decision"]["guard_cost"] == "within margin"
    assert s["comparisons"]["cost_none_vs_v3"]["a_only"] == 0


@pytest.mark.unit
def test_cost_exceeds_margin_when_the_guard_breaks_many_tasks():
    s = S4["score_rows"](_benign(10, 15, 75))
    assert s["decision"]["guard_cost"] == "exceeds margin or undetermined"


@pytest.mark.unit
def test_out_of_scope_injection_tasks_are_left_out_of_the_attack_comparison():
    rows = _benign(5, 0, 5)
    for i in range(12):  # in scope: the attack succeeds without the guard, not with it
        rows += _ep("banking", f"a{i}", "injection_task_0",
                    {"none": (False, True), "v2": (False, False), "v3": (False, False)})
    for i in range(30):  # out of scope by design: succeeds with or without the guard
        rows += _ep("slack", f"o{i}", "injection_task_3", {"none": (False, True), "v2": (False, True), "v3": (False, True)})
    s = S4["score_rows"](rows)
    assert s["episodes"]["attacked_in_scope"] == 12
    assert s["decision"]["attacks"] == "guard stops significantly more"
    assert s["attack_success_all"]["v3"]["k"] == 30


@pytest.mark.unit
def test_no_successful_attacks_is_said_so():
    rows = _benign(5, 0, 5) + _ep("banking", "a", "injection_task_0",
                                  {"none": (True, False), "v2": (True, False), "v3": (True, False)})
    assert S4["score_rows"](rows)["decision"]["attacks"] == "no successful attacks to stop"


@pytest.mark.unit
def test_an_episode_missing_an_arm_is_counted_not_scored():
    rows = _benign(3, 0, 0) + [{"suite": "x", "user_task": "y", "injection_task": None, "arm": "none",
                                 "utility": True, "security": None}]
    s = S4["score_rows"](rows)
    assert s["episodes"]["incomplete"] == 1 and s["episodes"]["benign"] == 3


EVIDENCE = ROOT / "evals/validation/v1/step4_agentdojo.json"


@pytest.mark.unit
@pytest.mark.skipif(not EVIDENCE.exists(), reason="step 4 has not been scored yet")
def test_the_committed_step4_result_re_derives_from_its_rows():
    import json

    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    again = S4["score_rows"](ev["rows"])
    for key in ("episodes", "utility_benign", "attack_success_in_scope", "comparisons", "decision"):
        assert again[key] == ev[key], key
    assert ev["guardrail_git_sha"] == S4["RULES_SHA"]
