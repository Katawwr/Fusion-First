"""TRUST_REPORT.md is generated from committed evidence: it must equal a fresh render."""

from __future__ import annotations

import json
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
    """The header promises five questions; each one is answered by a Q section (Q2: does it error?)."""
    out = render()
    assert "Five questions about Fusion itself" in out.split("## Bottom line")[0]
    for q in ("## Q1: ", "## Q2: ", "## Q3: ", "## Q4: ", "## Q5: "):
        assert q in out
    assert "rules_git_sha" not in out and "`fusion/guardrail`" not in out


# ---------------------------------------------------------------- Q5: the trained detector (PREREG_detector_v1.md)

DIGEST = "ab" * 32
Q5 = "## Q5: Does a trained detector beat the phrase list on injected tool results?"


def _q5_section(out: str) -> str:
    return out.split(Q5)[1].split("\n## ")[0]


def _seal(root):
    seal = root / "evals/validation/v1/detector/confirmatory.seal.json"
    seal.parent.mkdir(parents=True, exist_ok=True)
    seal.write_text(json.dumps({"digest": DIGEST, "format": "fusion.seal/v1", "rows": {}}), encoding="utf-8")


def _detector_envelope(adopt: bool) -> dict:
    """A synthetic envelope written by the scorer's own `build_envelope` (no model is called)."""
    from fusion_first.validate.detector_confirmatory import build_envelope

    rows = []
    for source, n_pos, n_neg in (("injecagent", 20, 20), ("bipia", 10, 6), ("deepset", 8, 8), ("blind", 0, 12)):
        rows += [{"id": f"{source}-{lab}-{i}", "source": source, "label": lab, "technique": f"{source}:t",
                  "text": f"{source} text {lab} {i}"} for lab, n in ((1, n_pos), (0, n_neg)) for i in range(n)]
    ids = [r["id"] for r in rows]

    def scores(flag) -> dict:
        return {r["id"]: (0.9 if flag(r) else 0.1) for r in rows}

    def nth(r) -> int:
        return int(r["id"].rsplit("-", 1)[1])

    caught = 16 if adopt else 8  # of the 20 InjecAgent positives, under the fold that never saw InjecAgent
    loso = scores(lambda r: r["label"] == 1 and (r["source"] != "injecagent" or nth(r) < caught))
    shipped = scores(lambda r: r["label"] == 1 or (r["source"] == "blind" and nth(r) < (1 if adopt else 4)))
    native = {"threshold": 1.0, "threshold_rule": "native_binary"}
    lg3_ids = [r["id"] for r in rows if nth(r) < 3]
    sources = ("injecagent", "bipia", "deepset", "blind")
    # arm F as registered: one hold-out-InjecAgent fold scores every confirmatory source (in-source outside InjecAgent)
    ft = scores(lambda r: (r["label"] == 1 and (r["source"] != "injecagent" or nth(r) < 5))
                or (r["source"] == "injecagent" and r["label"] == 0 and nth(r) < 1))
    ft_fold = {"folds": dict.fromkeys(sources, "finetune_holdout_injecagent"),
               "fold_thresholds": dict.fromkeys(sources, 0.5)}
    arms = {
        "b0_always_negative": {"scores": dict.fromkeys(ids, 0.0), "thresholds": dict.fromkeys(ids, 1.0),
                               "label": "B0 always-negative", "note": "never flags", **native},
        "b1_phrase_list": {"scores": {r["id"]: float(r["label"] == 1 and nth(r) < 2) for r in rows},
                           "thresholds": dict.fromkeys(ids, 1.0), "label": "B1 phrase list", "note": "n",
                           "latency_ms": [0.004] * len(ids), **native},
        "embed": {"scores": loso, "thresholds": dict.fromkeys(ids, 0.5), "label": "E LOSO", "threshold": None,
                  "threshold_rule": "fpr", "note": "n"},
        "embed_all": {"scores": shipped, "thresholds": dict.fromkeys(ids, 0.5), "label": "E all", "threshold": 0.5,
                      "threshold_rule": "fpr", "note": "n", "latency_ms": [12.0, 14.0, 30.0]},
        "finetune": {"scores": ft, "thresholds": dict.fromkeys(ids, 0.5), "label": "F folds", "threshold": None,
                     "threshold_rule": "fpr", "note": "n", **ft_fold},
        "finetune_all": {"scores": scores(lambda r: r["label"] == 1), "thresholds": dict.fromkeys(ids, 0.5),
                         "label": "F all", "threshold": 0.5, "threshold_rule": "fpr", "note": "n",
                         "latency_ms": [40.0, 44.0, 50.0]},
        "llama_guard3_configured": {"ids": lg3_ids, "scores": {i: (None if i == lg3_ids[0] else 1.0) for i in lg3_ids},
                                    "thresholds": dict.fromkeys(lg3_ids, 1.0), "label": "B2 LG3 configured",
                                    "note": "n", "latency_ms": [2400.0] * 5, "subsample_n": len(lg3_ids), **native},
        # a run that returned no parseable reply: n_scored 0, so no table row and every row counted unscored
        "llama_guard3_default": {"ids": lg3_ids, "scores": dict.fromkeys(lg3_ids), "label": "B2 LG3 default",
                                 "thresholds": dict.fromkeys(lg3_ids, 1.0), "note": "n", "subsample_n": len(lg3_ids),
                                 **native},
        "zeta_arm": {"scores": shipped, "thresholds": dict.fromkeys(ids, 0.5), "label": "Z an arm added later",
                     "threshold": 0.5, "threshold_rule": "fpr", "note": "n"},
    }
    absent = {"protectai_deberta": "needs the owner's approval"}
    env, _ = build_envelope(rows, arms, digest=DIGEST, absent=absent,
                            meta={"measured": "2026-10-18", "git_sha": "0" * 40, "frame": "[REQUEST] [TOOL] [RESULT]"})
    return json.loads(json.dumps(env))


@pytest.mark.unit
def test_q5_says_the_registered_study_is_not_yet_scored_without_its_evidence(tmp_path):
    from fusion_first.validate.trust_report import evidence_json

    _seal(tmp_path)
    out = render(tmp_path)
    q5 = _q5_section(out)
    assert "REGISTERED, NOT YET SCORED" in q5 and "`evals/validation/v1/PREREG_detector_v1.md`" in q5
    assert f"(seal `{DIGEST}`)" in q5 and "| Source |" not in q5
    bottom = out.split("## Q1")[0]
    assert "**Trained detector for injected tool results?** Registered in" in bottom and "not yet scored" in bottom
    assert evidence_json(tmp_path)["detector"] is None
    # demonstration evidence is not trust evidence: still registered, not scored
    env = {**_detector_envelope(True), "demonstration": True}
    (tmp_path / "evals/validation/v1/detector/detector_v1.json").write_text(json.dumps(env), encoding="utf-8")
    assert "REGISTERED, NOT YET SCORED" in _q5_section(render(tmp_path))
    assert evidence_json(tmp_path)["detector"] is None


@pytest.mark.unit
@pytest.mark.parametrize("adopt", [True, False])
def test_q5_reports_every_arm_by_source_with_the_registered_decision(tmp_path, adopt):
    from fusion_first.validate.trust_report import evidence_json

    _seal(tmp_path)
    env = _detector_envelope(adopt)
    assert env["decision"]["adopt"] is adopt
    (tmp_path / "evals/validation/v1/detector/detector_v1.json").write_text(json.dumps(env), encoding="utf-8")
    out = render(tmp_path)
    q5 = _q5_section(out)
    assert "`evals/validation/v1/detector/detector_v1.json`" in q5 and f"(seal `{DIGEST}`)" in q5
    rows = [[c.strip() for c in line.split("|")[1:-1]] for line in q5.splitlines() if line.startswith("| ")]
    head, rows = rows[0], rows[1:]
    assert head[:3] == ["Source", "Arm", "Injected texts flagged (recall)"] and "p50 latency" in head
    by = {(r[0], r[1]): r for r in rows}
    # sources in the registered order, and every arm present under each source it scored
    assert [r[0] for r in rows] == sorted((r[0] for r in rows), key=["InjecAgent (unspent)", "BIPIA in carriers",
                                          "deepset test (in-distribution)", "Blind negatives"].index)
    ft, ft_in, ft_all = "F fine-tune, hold-out-InjecAgent fold", "F fine-tune, hold-out-InjecAgent fold (in-source)", \
        "F fine-tune, all sources (in-source)"
    shipped = "E embedding, all sources, shipped (in-source)"
    # an arm the report does not know keeps its own label; an arm with no scored row has no table row
    assert {a for _, a in by} == {"B0 always negative", "B1 phrase list (shipped)", "E embedding, leave-one-source-out",
                                  shipped, ft, ft_in, ft_all, "B2 Llama Guard 3, configured", "Z an arm added later"}
    assert not [a for _, a in by if "off the shelf" in a]
    # in-source marks: every all-sources row; arm F everywhere but InjecAgent (its hold-out-InjecAgent fold scores
    # every source); never the leave-one-source-out arm
    assert {s for s, a in by if a == ft} == {"InjecAgent (unspent)"}
    assert {s for s, a in by if a == ft_in} == {"BIPIA in carriers", "deepset test (in-distribution)", "Blind negatives"}
    assert len([1 for _, a in by if a in (shipped, ft_all)]) == 8
    assert by[("InjecAgent (unspent)", ft)][2].startswith("5 of 20, ") and by[("InjecAgent (unspent)", ft)][3].startswith(
        "1 of 20, ")
    assert by[("InjecAgent (unspent)", ft_all)][6] == "44 ms"
    loso = by[("InjecAgent (unspent)", "E embedding, leave-one-source-out")]
    assert loso[2].startswith(f"{16 if adopt else 8} of 20, ")
    assert by[("InjecAgent (unspent)", "B1 phrase list (shipped)")][2].startswith("2 of 20, ")
    assert by[("InjecAgent (unspent)", "B1 phrase list (shipped)")][6] == "<0.01 ms"
    assert by[("InjecAgent (unspent)", shipped)][6] == "14 ms"
    lg3 = by[("InjecAgent (unspent)", "B2 Llama Guard 3, configured")]
    assert lg3[2].startswith("2 of 2, ") and lg3[6] == "2.4 s"  # its own subsample; the unscored row is excluded
    blind = by[("Blind negatives", shipped)]
    assert blind[2] == "–" and blind[3].startswith(f"{1 if adopt else 4} of 12, ") and blind[4] == "12"
    assert blind[5] == "–"  # no positives, no AUROC
    bullets = [line for line in q5.splitlines() if line.startswith("- ")]
    decision = next(line for line in bullets if line.startswith("- Registered decision:"))
    verdict = "adopted as an observe-only `guard_input` signal" if adopt else "not adopted: the detector stays dev-only"
    assert f"**{verdict}**" in decision
    assert f"{(16 if adopt else 8) / 20 * 100:.1f}%" in decision and "at least 0.60" in decision
    assert "on the 38 distinct benign tool results" in decision and "at most 0.05" in decision
    unseen = next(line for line in bullets if line.startswith("- Never-seen InjecAgent injections"))
    assert f"E leave-one-source-out {16 if adopt else 8} of 20 flagged ({(16 if adopt else 8) * 5:.1f}%)" in unseen
    assert "F hold-out-InjecAgent fold 5 of 20 flagged (25.0%), 1 of 20 false alarms (5.0%)" in unseen
    assert "B2 Llama Guard 3 configured, on its subsample, 2 of 2 flagged" in unseen
    assert "all-sources" not in unseen and "B0" not in unseen
    seen = next(line for line in bullets if line.startswith("- In-source InjecAgent rows:"))
    assert "the E all-sources model 20 of 20 flagged (100.0%); the F all-sources model 20 of 20 flagged" in seen
    assert "62 attacker instructions and 17 tool-result templates" in seen
    # the claimed primaries include the shipped (in-source) model's FPR: LOSO recall is the only generalisation claim
    assert "leave-one-source-out recall is the only generalisation claim" in seen and "claims only" not in q5
    unscored = next(line for line in bullets if line.startswith("- Unscored rows"))
    assert ("B2 Llama Guard 3, configured 1 of 21; B2 Llama Guard 3, off the shelf 21 of 21; a source with no scored "
            "text has no table row.") in unscored
    assert "- Registered arms not run: B3 ProtectAI deberta-v3." in q5
    limits = next(line for line in bullets if line.startswith("- Limits registered before data:"))
    for word in ("adaptive", "in-distribution", "dev-only"):
        assert word in limits
    assert ("leave-one-source-out recall is the only generalisation claim; the shipped model's false-positive rate and "
            "the baselines' rows are registered measurements on the sealed rows and say nothing about unseen "
            "sources") in limits
    assert ("the E all-sources model and the F all-sources model on every source; F hold-out-InjecAgent fold on BIPIA, "
            "deepset and blind (`finetune_holdout_injecagent` trained on their dev rows)") in limits
    bottom = out.split("## Q1")[0]
    line = next(x for x in bottom.splitlines() if x.startswith("- **Trained detector for injected tool results?**"))
    assert f"it flagged {16 if adopt else 8} of 20, {(16 if adopt else 8) * 5:.1f}% (" in line
    assert "the phrase list flagged 2 of 20" in line
    assert ("Registered decision: adopted as an observe-only" if adopt else "not adopted: the detector stays dev-only") \
        in line
    site = evidence_json(tmp_path)["detector"]
    assert site["decision"]["adopt"] is adopt and site["seal_digest"] == DIGEST
    assert site["preregistration"] == "evals/validation/v1/PREREG_detector_v1.md"
    assert site["primary"]["injecagent_recall"]["n"] == 20 and site["primary"]["shipped_fpr"]["n"] == 38
    assert [a["arm"] for a in site["absent"]] == ["protectai_deberta"]
    rows = {(r["source"], r["arm"]): r for r in site["rows"]}
    assert rows[("injecagent", "embed")]["recall"]["point"] == pytest.approx((16 if adopt else 8) / 20)
    assert set(rows[("blind", "embed_all")]["fpr"]) >= {"point", "low", "high"}
    assert rows[("blind", "embed_all")]["recall"] is None  # no positives: no rate, not a 0% (0%–100%)
    assert [k for k, r in rows.items() if r["in_source"] and k[1] == "finetune"] == [
        ("bipia", "finetune"), ("deepset", "finetune"), ("blind", "finetune")]
    assert not rows[("injecagent", "finetune")]["in_source"] and rows[("injecagent", "finetune_all")]["in_source"]
    assert not any(arm == "llama_guard3_default" for _, arm in rows)
    unsc = {u["arm"]: (u["unscored"], u["n_rows"]) for u in site["unscored"]}
    assert unsc["llama_guard3_default"] == (21, 21) and unsc["llama_guard3_configured"] == (1, 21)
    assert unsc["finetune"] == (0, 84) and unsc["finetune_all"] == (0, 84)


@pytest.mark.unit
def test_q5_says_when_no_arm_left_a_row_unscored(tmp_path):
    env = _detector_envelope(False)
    for key in ("llama_guard3_configured", "llama_guard3_default"):
        del env["arms"][key]
    (tmp_path / "evals/validation/v1/detector").mkdir(parents=True)
    (tmp_path / "evals/validation/v1/detector/detector_v1.json").write_text(json.dumps(env), encoding="utf-8")
    q5 = _q5_section(render(tmp_path))
    assert "- Unscored rows (no finite score; excluded from that arm's rates): none in any arm." in q5
    assert "Llama Guard" not in q5  # no subsample clause without a Llama Guard arm


@pytest.mark.unit
def test_the_detector_doc_table_is_one_row_per_arm_scored_on_injecagent():
    """docs/DETECTOR.md's summary: InjecAgent recall, false positives on the tool-result negatives (InjecAgent, blind,
    BIPIA; never deepset), InjecAgent AUROC and p50, in-source marked; an arm without a scored InjecAgent row is out.
    A fold arm whose scoring fold trained on some of those sources splits its benign cell into never-seen and
    in-source rows (arm F: InjecAgent never seen; blind and BIPIA carrier controls in-source)."""
    from fusion_first.validate.trust_report import detector_doc_table

    lines = detector_doc_table(_detector_envelope(False)).splitlines()
    assert lines[0].startswith("| Arm | InjecAgent injections flagged | Benign tool results flagged |")
    by = {line.split(" | ")[0][2:]: line for line in lines[2:]}
    assert "B2 Llama Guard 3, off the shelf" not in by
    assert by["E embedding, all sources, shipped (in-source)"] == \
        "| E embedding, all sources, shipped (in-source) | 20 of 20 (100.0%) | 4 of 38 (10.5%) | 1.00 | 14 ms |"
    assert by["F fine-tune, hold-out-InjecAgent fold"].startswith(
        "| F fine-tune, hold-out-InjecAgent fold | 5 of 20 (25.0%) | 1 of 20 (5.0%) never-seen, 0 of 18 (0.0%) "
        "in-source |")
    assert by["E embedding, leave-one-source-out"].split(" | ")[2] == "0 of 38 (0.0%)"  # never in-source: one count
    assert by["B2 Llama Guard 3, configured"].split(" | ")[2] == "9 of 9 (100.0%)"  # its subsample's tool-result rows


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
