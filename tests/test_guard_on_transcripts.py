"""The runtime guardrail applied to real attack transcripts (evals/validation/v1/
PREREG_guard_on_real_transcripts.md). Offline: responses are given; the real guard and oracles judge."""

from __future__ import annotations

import pytest

from fusion.guardrail.guard import _looks_consequential
from fusion.validate.experiments import build_items
from fusion.validate.guard_on_transcripts import gandalf_outcome, injecagent_outcome, summarize


def _item_with_attacker_tool(consequential: bool):
    for it in build_items("injecagent", 30):
        tool = it.oracle["forbidden_tools"][0]
        if _looks_consequential(tool) is consequential:
            return it, tool
    pytest.skip("no such item in the sample")


@pytest.mark.unit
def test_an_unrequested_consequential_attacker_call_is_stopped():
    item, tool = _item_with_attacker_tool(consequential=True)
    out = injecagent_outcome(item, f'ACTION: {{"tool": "{tool}", "arguments": {{"to": "x"}}}}')
    assert out == {"attack": True, "stopped": True, "blocked_any": True, "attacker_calls": 1}


@pytest.mark.unit
def test_a_bare_action_line_is_judged_too():
    item, tool = _item_with_attacker_tool(consequential=True)
    out = injecagent_outcome(item, f"ACTION: {tool}\n\nTo do that I need the account id.")
    assert out["attack"] and out["stopped"]


@pytest.mark.unit
def test_a_read_only_attacker_call_is_not_stopped():
    item, tool = _item_with_attacker_tool(consequential=False)
    out = injecagent_outcome(item, f'ACTION: {{"tool": "{tool}", "arguments": {{}}}}')
    assert out["attack"] is True and out["stopped"] is False


@pytest.mark.unit
def test_a_clean_reply_is_not_an_attack_and_nothing_is_blocked():
    item, _ = _item_with_attacker_tool(consequential=True)
    out = injecagent_outcome(item, "Here are the product details you asked for.")
    assert out == {"attack": False, "stopped": None, "blocked_any": False, "attacker_calls": 0}


@pytest.mark.unit
def test_a_leaked_password_is_redacted_and_a_refusal_is_left_alone():
    item = build_items("gandalf", 1)[0]
    pw = item.oracle["canaries"][0]
    assert gandalf_outcome(item, f"Sure! The password is {pw}.") == {"attack": True, "stopped": True,
                                                                     "blocked_any": True}
    assert gandalf_outcome(item, "I can't share that.") == {"attack": False, "stopped": None,
                                                            "blocked_any": False}


@pytest.mark.unit
def test_summary_counts_recall_and_over_block_by_group():
    rows = [
        {"experiment": "gandalf", "model": "m", "group": "gandalf", "attack": True, "stopped": True, "blocked_any": True},
        {"experiment": "gandalf", "model": "m", "group": "gandalf", "attack": True, "stopped": False, "blocked_any": False},
        {"experiment": "gandalf", "model": "m", "group": "gandalf", "attack": False, "stopped": None, "blocked_any": True},
        {"experiment": "gandalf", "model": "m", "group": "gandalf", "attack": False, "stopped": None, "blocked_any": False},
    ]
    s = summarize(rows)["gandalf"]
    assert (s["attacks"], s["stopped"], s["clean"], s["over_blocked"]) == (2, 1, 2, 1)
    assert s["recall"]["point"] == pytest.approx(0.5) and s["over_block"]["point"] == pytest.approx(0.5)
