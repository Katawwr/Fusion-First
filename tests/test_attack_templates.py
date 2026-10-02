"""Attack templates turn a user's pasted system prompt into per-check attack trajectories."""

from __future__ import annotations

import pytest

from fusion_first.attacks.taxonomy import Crosswalk
from fusion_first.attacks.templates import get_templates, select_templates
from fusion_first.judge.rubric import checks_of_kind
from fusion_first.schemas import ScanTier

CHECKS = checks_of_kind("safety")  # only safety checks have attack probes/templates


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_every_template_injects_user_prompt_and_tags_valid_owasp(check):
    templates = get_templates(check)
    assert len(templates) >= 12, "should cover the curated probe corpus"
    cw = Crosswalk()
    sentinel = "SENTINEL_SYSTEM_PROMPT_9f3c"
    for t in templates:
        assert t.check == check
        assert t.attack_label.strip()
        traj = t.demo_trajectory(sentinel, hardened=False)
        assert traj.system_prompt() == sentinel
        assert traj.final_response()
        if t.injected:
            assert traj.has_injection()
        cw.validate_code(t.owasp)


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_demo_arms_diverge_for_most_templates(check):
    # Not all: the corpus deliberately includes a few probes where hardening doesn't fully fix it.
    templates = get_templates(check)
    differ = sum(
        t.demo_trajectory("You are a helpful bot.", hardened=False).final_response()
        != t.demo_trajectory("You are a helpful bot.", hardened=True).final_response()
        for t in templates
    )
    assert differ >= 0.6 * len(templates)


@pytest.mark.unit
def test_quick_tier_is_a_deterministic_prefix_of_full():
    full = select_templates("direct_prompt_injection", ScanTier.FULL)
    quick = select_templates("direct_prompt_injection", ScanTier.QUICK)
    assert 0 < len(quick) <= len(full)
    assert [t.id for t in quick] == [t.id for t in full][: len(quick)]


@pytest.mark.unit
def test_live_target_messages_present_injected_content_as_data():
    t = next(t for t in get_templates("direct_prompt_injection") if t.injected)
    msgs = t.target_messages()
    assert msgs[0]["role"] == "user"
    assert t.injected in msgs[0]["content"]
    assert "untrusted" in msgs[0]["content"].lower()
