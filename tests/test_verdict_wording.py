"""The verdict strings agents quote to users (audit_agent's `verdict`, finalize_run's `verdict`) lead with
the runtime guardrail and call the prompt fix optional."""

from __future__ import annotations

import pytest

from fusion_first.integrations.agent_tools import _plain_verdict
from fusion_first.runs.service import _verdict


@pytest.mark.unit
def test_the_audit_verdict_offers_the_guardrail_first_and_the_fix_as_optional():
    v = _plain_verdict({"checks": [{"label": "Prompt injection", "baseline_issue_rate": 0.5}],
                        "overall_grade": "F", "demonstration": False})
    assert "Add the runtime guardrail" in v and "optional" in v
    assert v.index("runtime guardrail") < v.index("prompt fix")
    assert "Apply the hardened prompt" not in v


def _card(honesty: str, as_written: float, with_fix: float) -> dict:
    return {"check": "direct_prompt_injection", "kind": "safety", "grade": "F", "grade_withheld": None,
            "honesty": honesty, "issue_rate_as_written": as_written, "issue_rate_with_fix": with_fix}


@pytest.mark.unit
@pytest.mark.parametrize(("honesty", "with_fix"), [("PRELIMINARY", 0.4), ("PROVEN", 0.1)])
def test_the_run_verdict_offers_the_guardrail_first_and_the_fix_as_optional(honesty, with_fix):
    v = _verdict("F", [_card(honesty, 0.6, with_fix)], has_safety=True)
    assert v.startswith("Grade F: problems found in direct_prompt_injection (F).")
    assert "Add the runtime guardrail" in v and "optional" in v
    assert v.index("runtime guardrail") < v.index("prompt fix")
    assert "Apply hardened_prompt" not in v
