"""TRUST_REPORT.md is generated from committed evidence: it must equal a fresh render."""

from __future__ import annotations

import pathlib

import pytest

from fusion_first.validate.trust_report import render

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_trust_report_matches_its_evidence():
    committed = (ROOT / "TRUST_REPORT.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render(ROOT), "regenerate with: python -m fusion_first.validate.trust_report"


@pytest.mark.unit
def test_demo_evidence_never_reaches_the_report(tmp_path):
    (tmp_path / "evals/guard_bench").mkdir(parents=True)
    (tmp_path / "evals/guard_bench/claude_code_heldout_v1.json").write_text(
        '{"demonstration": true, "benign": {"n": 1}}', encoding="utf-8")
    out = render(tmp_path)
    assert "NOT YET MEASURED" in out and "| v1 |" not in out


def _rate(k, n):
    return {"point": k / n, "low": max(0.0, k / n - 0.1), "high": min(1.0, k / n + 0.1), "k": k, "n": n}


def _pooled(k_base, k_fix, n, ci_low, ci_high):
    red = (k_base - k_fix) / n
    return {"models": ["m1", "m2"], "kind": "safety", "n_pairs": n,
            "baseline_rate": _rate(k_base, n), "hardened_rate": _rate(k_fix, n),
            "before_after": {"absolute_reduction": {"point": red, "low": ci_low, "high": ci_high},
                             "mcnemar_p": 0.5, "honesty": "INCONCLUSIVE"},
            "reduction_cluster_ci": {"point": red, "low": ci_low, "high": ci_high}}


def _cell(exp, model, k_base, k_fix, n, p):
    return {"experiment": exp, "model": model, "kind": "safety", "n_items": n, "n_paired": n,
            "n_unscored": 0, "n_undecidable": 0, "n_truncated": 0,
            "baseline_rate": _rate(k_base, n), "hardened_rate": _rate(k_fix, n),
            "before_after": {"absolute_reduction": {"point": (k_base - k_fix) / n, "low": -1, "high": 1},
                             "mcnemar_p": p, "honesty": "INCONCLUSIVE"}}


@pytest.mark.unit
def test_fix_evidence_is_summarised_pooled_over_models(tmp_path):
    import json

    ev = {
        "demonstration": False, "models": {"m1": "d1", "m2": "d2"},
        "cells": [_cell("xstest", "m1", 3, 10, 30, 0.02), _cell("xstest", "m2", 3, 4, 30, 1.0)],
        "pooled": {
            # the interval of the REDUCTION (as written minus with fix) decides the verdict
            "xstest": _pooled(6, 14, 60, -0.25, -0.03),
            "gandalf": _pooled(12, 11, 60, -0.08, 0.10),
            "injecagent": _pooled(20, 8, 60, 0.05, 0.35),
        },
    }
    (tmp_path / "evals/validation/v1").mkdir(parents=True)
    (tmp_path / "evals/validation/v1/evidence_oracle.json").write_text(json.dumps(ev), encoding="utf-8")
    out = render(tmp_path)
    rows = {line.split("|")[1].strip(): line for line in out.splitlines() if line.startswith("| ")}
    assert "significantly worse with the fix" in rows["xstest (pooled)"]
    assert "no clear change" in rows["gandalf (pooled)"]
    assert "significantly better with the fix" in rows["injecagent (pooled)"]
    assert "xstest on m1" in out.split("## Q1")[0]  # the bottom line names the model, not just the test
    from fusion_first.validate.trust_report import evidence_json

    pooled = {p["experiment"]: p for p in evidence_json(tmp_path)["fix_pooled"]}
    assert pooled["xstest"]["verdict"] == "significantly worse with the fix"
    assert pooled["xstest"]["change"]["point"] == pytest.approx(8 / 60)  # issue-rate change, fix minus as written


def _b3_block(n, rubric_acc, plain_acc, low, high, p, unanswered=0):
    acc = lambda a: {"accuracy": {"point": a, "low": a - 0.1, "high": min(1.0, a + 0.05)}}  # noqa: E731
    return {"n": n, "b3_unanswered": unanswered, "rubric": acc(rubric_acc), "b3": acc(plain_acc),
            "accuracy_difference": {"point": rubric_acc - plain_acc, "low": low, "high": high},
            "mcnemar_p": p, "rubric_right_b3_wrong": 4, "b3_right_rubric_wrong": 5}


@pytest.mark.unit
@pytest.mark.parametrize("claim", [False, True])
def test_rubric_vs_plain_judge_is_reported_with_its_preregistered_verdict(tmp_path, claim):
    import json

    pooled = _b3_block(119, 0.86, 0.87, -0.06, 0.04, 1.0, 1) if not claim else _b3_block(119, 0.9, 0.7, 0.1, 0.3, 0.001)
    b3 = {"demonstration": False, "by_check": {"direct_prompt_injection": pooled}, "pooled": pooled,
          "sensitivity_unanswered_as_wrong": pooled, "decision": {"claim_allowed": claim, "rule": "r"}}
    (tmp_path / "evals/validation/v1").mkdir(parents=True)
    (tmp_path / "evals/validation/v1/b3_rubric_vs_plain_judge.json").write_text(json.dumps(b3), encoding="utf-8")
    out = render(tmp_path)
    rows = {line.split("|")[1].strip(): line for line in out.splitlines() if line.startswith("| ")}
    rubric_pct, plain_pct = ("90%", "70%") if claim else ("86%", "87%")
    assert rubric_pct in rows["pooled"] and plain_pct in rows["pooled"]
    if claim:
        assert "significantly more accurate than a plain" in out
    else:
        assert "not significantly more accurate than asking the same model one plain question" in out
    from fusion_first.validate.trust_report import evidence_json

    site = evidence_json(tmp_path)["rubric_vs_plain"]
    assert site["claim_allowed"] is claim and site["pooled"]["n"] == 119
    assert site["pooled"]["rubric"]["point"] == pytest.approx(0.86 if not claim else 0.9)


def _guard_set(prompted, n_benign, caught, n_attack):
    return {"demonstration": False, "benign": {"n": n_benign, "prompted": prompted,
            "over_block": {"point": prompted / n_benign, "ci95": [0.0, 0.2]}},
            "malicious": {"n": n_attack, "caught": caught, "recall": {"point": caught / n_attack, "ci95": [0.2, 0.9]}},
            "status": "HELD OUT at rules_git_sha. Any rule change after this measurement makes it a dev set."}


@pytest.mark.unit
def test_only_the_newest_held_out_guard_set_is_reported_and_older_ones_are_listed_for_audit(tmp_path):
    import json

    from fusion_first.validate.trust_report import evidence_json

    (tmp_path / "evals/guard_bench").mkdir(parents=True)
    for v, ev in (("v2", _guard_set(5, 100, 23, 70)), ("v3", _guard_set(2, 100, 49, 70))):
        (tmp_path / f"evals/guard_bench/claude_code_heldout_{v}.json").write_text(json.dumps(ev), encoding="utf-8")
    out = render(tmp_path)
    rows = {line.split("|")[1].strip(): line for line in out.splitlines() if line.startswith("| v")}
    assert set(rows) == {"v3"} and "held out, scored once" in rows["v3"]  # v2 was scored against rules changed since
    assert "rules_git_sha" not in out  # a field name never reaches the report; the sha does
    bottom = out.split("## Q1")[0]
    assert "70%" in bottom and "2%" in bottom  # v3's recall and over-block, not v2's
    audit = out.rstrip().splitlines()[-1]
    assert audit.startswith("Superseded evidence kept for audit:") and "claude_code_heldout_v2.json" in audit
    assert "claude_code_heldout_v3.json" not in audit
    assert [g["set"] for g in evidence_json(tmp_path)["guard_heldout"]] == ["v3"]


def _attack(k_base, k_fix, n, p, fixed, broke):
    return {"n_pairs": n, "baseline_rate": _rate(k_base, n), "treatment_rate": _rate(k_fix, n),
            "before_after": {"mcnemar_p": p, "discordant_b": fixed, "discordant_c": broke}}


@pytest.mark.unit
@pytest.mark.parametrize("adopt", [False, True])
def test_the_preregistered_compact_fix_is_one_sentence_with_its_decision(tmp_path, adopt):
    import json

    per_model = {"m1": {"attack_lower": adopt, "attack_higher": False, "over_refusal_noninferior": True,
                        "both_primary": adopt},
                 "m2": {"attack_lower": False, "attack_higher": False, "over_refusal_noninferior": False,
                        "both_primary": False}}
    ev = {"demonstration": False, "arms": ["baseline", "compact"], "models": {"m1": "d", "m2": "d"},
          "attack_success_by_model": {"m1": _attack(20, 8, 60, 0.004 if adopt else 0.3, 13, 1),
                                      "m2": _attack(12, 11, 60, 1.0, 3, 2)},
          "prereg_decision": {"adopt": adopt, "rule": "r", "per_model": per_model}}
    fix = {"demonstration": False, "models": {"m1": "d"}, "cells": [_cell("xstest", "m1", 3, 10, 30, 0.02)]}
    v1 = tmp_path / "evals/validation/v1"
    v1.mkdir(parents=True)
    (v1 / "compact_fix.json").write_text(json.dumps(ev), encoding="utf-8")
    (v1 / "evidence_oracle.json").write_text(json.dumps(fix), encoding="utf-8")
    out = render(tmp_path)
    q3 = out.split("## Q3")[1]
    assert ("compact version of the fix" in q3) and ("was adopted" if adopt else "was not adopted") in q3
    assert "evals/validation/v1/compact_fix.json" in q3
    assert not any(line.startswith("| m1 |") for line in out.splitlines())  # no table of its own
    assert "compact fix for small models" not in out


def _judge_block(acc, f1):
    r = lambda p: {"point": p, "low": max(0.0, p - 0.1), "high": min(1.0, p + 0.1)}  # noqa: E731
    return {"grader": {"n": 60, "unanswered": 0, "accuracy": r(acc), "recall": r(0.8), "specificity": r(0.8),
                       "f1": f1, "kappa": 0.5},
            "naive_regex": {"f1": 0.5, "vs_grader": {"mcnemar_p": 0.3}},
            "tuned_heuristic": {"f1": 0.55, "vs_grader": {"mcnemar_p": 0.4}}}


@pytest.mark.unit
@pytest.mark.parametrize("meets", [True, False])
def test_the_free_local_grader_is_reported_against_its_registered_floor(tmp_path, meets):
    import json

    v1 = tmp_path / "evals/validation/v1"
    v1.mkdir(parents=True)
    host = {"demonstration": False, "grader": "Claude Sonnet (host)",
            "audit": {"method": "an LLM reading", "summary": {"disagreements": 3}},
            "checks": {"direct_prompt_injection": _judge_block(0.80, 0.67),
                       "system_prompt_leakage": _judge_block(0.92, 0.90)}}
    local = {"demonstration": False, "grader": "qwen2.5:7b probability judge (local)",
             "checks": {"direct_prompt_injection": _judge_block(0.75, 0.70 if meets else 0.40),
                        "system_prompt_leakage": _judge_block(0.62, 0.80)}}
    # a rule-based baseline significantly MORE accurate than the local grader on the same items
    local["checks"]["system_prompt_leakage"]["naive_regex"] = {"f1": 0.42, "accuracy": {"point": 0.82},
                                                              "vs_grader": {"mcnemar_p": 0.009}}
    (v1 / "judge_eval_host_sonnet.json").write_text(json.dumps(host), encoding="utf-8")
    (v1 / "judge_eval_prob_qwen7b.json").write_text(json.dumps(local), encoding="utf-8")
    out = render(tmp_path)
    q1 = out.split("## Q1")[1].split("## Q3")[0]
    assert "PREREG_local_grader.md" in q1
    assert ("stays the default free grader" in q1) is meets
    assert ("no longer recommends it by default" in q1) is (not meets)
    lines = q1.splitlines()
    rows = [i for i, line in enumerate(lines) if line.startswith("| `evals/")]
    assert rows == list(range(rows[0], rows[0] + 4))  # one unbroken table; audits come after it
    assert "**qwen2.5:7b probability judge (local):** 1 of 4" in q1 and "all against the grader" in q1
    assert "**Claude Sonnet (host):** None of the 4" in q1
    bottom = out.split("## Q1")[0]  # each grader named with its own numbers, never merged
    assert "Claude Sonnet (host)" in bottom and "The free local grader, qwen2.5:7b probability judge (local)," in bottom
    from fusion_first.validate.trust_report import evidence_json

    site = evidence_json(tmp_path)["local_grader"]
    assert site["meets_floor"] is meets and site["evidence"] == "evals/validation/v1/judge_eval_prob_qwen7b.json"
    rows = {(r["grader"], r["check"]): r for r in evidence_json(tmp_path)["judge_accuracy"]}
    # the website gets the direction too, so "significant" is never read as "better"
    worse = rows[("qwen2.5:7b probability judge (local)", "system_prompt_leakage")]["baselines"]["naive_regex"]
    assert worse == {"f1": 0.42, "mcnemar_p": 0.009, "grader_more_accurate": False}
    assert rows[("Claude Sonnet (host)", "direct_prompt_injection")]["baselines"]["naive_regex"]["grader_more_accurate"]


@pytest.mark.unit
def test_website_evidence_matches_its_sources():
    import json

    from fusion_first.validate.trust_report import evidence_json

    committed = json.loads((ROOT / "frontend/src/content/evidence.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(evidence_json(ROOT))), \
        "regenerate with: python -m fusion_first.validate.trust_report"


@pytest.mark.unit
def test_every_question_in_the_header_has_its_section():
    """The header promises four questions; each one is answered by a Q section (Q2: does it error?)."""
    out = render()
    for q in ("## Q1: ", "## Q2: ", "## Q3: ", "## Q4: "):
        assert q in out
    assert "rules_git_sha" not in out and "`fusion/guardrail`" not in out


@pytest.mark.unit
def test_superseded_evidence_is_listed_for_audit_not_reported():
    """Measurements on rules since replaced, or superseded on the same comparator, stay in the repo for audit,
    named once at the end of the report; neither the report nor the site presents them as results."""
    import json

    from fusion_first.validate.trust_report import evidence_json

    out = render()
    for gone in ("Runtime guardrail on real attacks", "Runtime guardrail vs Llama Guard 3", "Value ledger",
                 "SUPERSEDED", "Secondary outcomes", "destination-parsing"):
        assert gone not in out
    assert out.rstrip().splitlines()[-1].startswith("Superseded evidence kept for audit: ")
    site = json.dumps(evidence_json(ROOT))
    for key in ("runtime_guardrail", "value_ledger", "guard_vs_llama_guard"):
        assert f'"{key}"' not in site
