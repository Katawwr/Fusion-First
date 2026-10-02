"""The user's gate config is validated: typos fail closed."""

from __future__ import annotations

import pathlib

import pytest
import yaml

from fusion_first.stats.gate import PolicyError, load_policy, validate_policy

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_committed_policy_is_valid():
    validate_policy(yaml.safe_load((ROOT / "evals/policy.yaml").read_text(encoding="utf-8")))
    assert load_policy("direct_prompt_injection")["min_judge_f1"] == 0.60


@pytest.mark.unit
@pytest.mark.parametrize(
    "data, match",
    [
        ({"defaults": {"min_judge_f": 0.9}}, "unknown key"),  # a typo
        ({"defaults": {"min_judge_f1": 1.5}}, r"\[0, 1\]"),
        ({"defaults": {"min_judge_f1": True}}, r"\[0, 1\]"),
        ({"defaults": {"require_before_after_honesty": "SURE"}}, "one of"),
        ({"checks": {"prompt_injection": {"min_judge_f1": 0.7}}}, "unknown check"),
        ({"default": {}}, "top-level"),
        ({"checks": {"excessive_agency": {"max_unscored": 0.1}}}, "unknown key"),
    ],
)
def test_malformed_policy_fails_closed(tmp_path, data, match):
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(PolicyError, match=match):
        load_policy("excessive_agency", path)
