"""The quality dimension (instruction_following) runs through the same engine as safety, but is
kept out of the safety attack-suite defaults (it has no OWASP mapping and no attack probes)."""

from __future__ import annotations

import pytest

from fusion_first.engine.fixes import apply_fix, guard_block
from fusion_first.goldset import load_gold
from fusion_first.judge.rubric import checks_of_kind, get_rubric


@pytest.mark.unit
def test_instruction_following_registered_as_quality():
    r = get_rubric("instruction_following")
    assert r.kind == "quality"
    assert r.owasp.llm is None and r.owasp.asi is None  # no OWASP mapping for quality
    assert len(r.criteria) >= 2


@pytest.mark.unit
def test_kind_split_is_clean():
    safety = checks_of_kind("safety")
    quality = checks_of_kind("quality")
    assert "instruction_following" in quality
    assert set(safety).isdisjoint(quality)
    assert len(safety) == 4
    for c in safety:
        assert get_rubric(c).owasp.llm


@pytest.mark.unit
def test_quality_gold_is_balanced_and_labelled():
    gold = load_gold("instruction_following")
    assert len(gold) >= 12
    issues = sum(1 for c in gold if c.oracle.is_issue)
    assert 0.3 <= issues / len(gold) <= 0.7  # balanced enough for an honest F1
    blind = [c for c in gold if c.split == "blind"]
    assert len(blind) >= 4
    assert any(c.oracle.is_issue for c in blind) and any(not c.oracle.is_issue for c in blind)


@pytest.mark.unit
def test_default_harden_is_safety_only_but_quality_hardens_on_request():
    default = apply_fix("You are a bot.")
    assert "Instruction following" not in default
    q = guard_block(["instruction_following"])
    assert "Follow the user's instructions" in q
