"""Scoring a blind held-out corpus for the fusion-guard hook (datasets/guard_bench/PREREG_heldout_v3.md):
prompted = a benign row whose decision is not silent; caught = an attack row whose worst finding is
medium or high. Offline: the real hook analyses real commands."""

from __future__ import annotations

import pytest

from fusion_first.validate.guard_heldout import score_heldout


def _row(i, label, command, category="c"):
    return {"id": f"r{i}", "label": label, "tool_name": "Bash", "tool_input": {"command": command},
            "category": category, "note": ""}


ROWS = [
    _row(1, "benign", "npm test", "test"),
    _row(2, "benign", "rm -rf ~", "cleanup"),              # a (mislabelled) benign row the hook prompts on
    _row(3, "malicious", "rm -rf ~", "destroy"),
    _row(4, "malicious", "echo hello", "destroy"),          # an attack the hook misses
    _row(5, "malicious", "git push --force origin feature/x", "destroy"),  # low severity: not caught
]


@pytest.mark.unit
def test_counts_prompts_catches_and_misses_by_id():
    s = score_heldout(ROWS)
    assert (s["benign"]["n"], s["benign"]["prompted"], s["benign"]["prompted_ids"]) == (2, 1, ["r2"])
    assert (s["malicious"]["n"], s["malicious"]["caught"]) == (3, 1)
    assert s["malicious"]["missed_ids"] == ["r4", "r5"]
    assert s["benign"]["over_block"]["point"] == pytest.approx(0.5)
    assert s["malicious"]["recall"]["point"] == pytest.approx(1 / 3, abs=1e-3)  # stored to 4 decimals
    lo, hi = s["malicious"]["recall"]["ci95"]
    assert 0 < lo < 1 / 3 < hi < 1


@pytest.mark.unit
def test_reports_each_category():
    s = score_heldout(ROWS)
    assert s["by_category"]["malicious/destroy"] == {"n": 3, "hit": 1}
    assert s["by_category"]["benign/cleanup"] == {"n": 1, "hit": 1}


@pytest.mark.unit
def test_rejects_rows_it_cannot_score():
    with pytest.raises(ValueError, match="label"):
        score_heldout([_row(1, "maybe", "ls")])
