"""Generate TRUST_REPORT.md and the site's evidence.json from committed, non-demonstration evidence.

Every figure is read from a file under `evals/`, named next to it; missing evidence is NOT YET MEASURED.
"""

from __future__ import annotations

import json
import pathlib

from fusion_first._data import data_root
from fusion_first.validate.prereg import LOCAL_GRADER_EVIDENCE, local_grader_decision

HEADER = """# Fusion First: Trust Report

Four questions about Fusion itself: **is it accurate, does it error, does the fix work, does it beat
simpler checks?** Generated from committed evidence by `python -m fusion_first.validate.trust_report`; a test
fails if this file and its evidence disagree. Intervals are 95% Wilson unless noted. Demonstration
evidence (the offline stand-in judge) is excluded.
"""


def _load(root: pathlib.Path, rel: str) -> dict | None:
    p = root / rel
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("demonstration") is not False:
        return None  # stand-in / demo evidence is not trust evidence
    return data


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def _iv(d: dict | None) -> str:
    if not d:
        return "–"
    point = d.get("point")
    lo, hi = d.get("low", (d.get("ci95") or [None, None])[0]), d.get("high", (d.get("ci95") or [None, None])[1])
    return f"{_pct(point)} ({_pct(lo)}–{_pct(hi)})"


PLAIN_EXPERIMENT = {
    "injecagent": "tool hijacking (InjecAgent)",
    "gandalf": "password leaks (Gandalf)",
    "xstest": "refusing safe requests (XSTest)",
    "ifeval": "missed instructions (IFEval)",
}


def _pooled_ci(p: dict) -> dict:
    """The REDUCTION (as written minus with fix), resampling whole items across models."""
    return p.get("reduction_cluster_ci") or p["before_after"]["absolute_reduction"]


def _pooled_verdict(ci: dict) -> str:
    if ci["low"] > 0:
        return "significantly better with the fix"
    if ci["high"] < 0:
        return "**significantly worse with the fix**"
    return "no clear change"


def _pp(x: float) -> str:
    return f"{x * 100:+.0f} pts"


def _pooled_sentence(fix: dict) -> str:
    pooled = fix.get("pooled") or {}
    if len(fix.get("models", {})) < 2 or not pooled:
        return ""
    groups: dict[str, list[str]] = {}
    for exp, p in pooled.items():
        groups.setdefault(_pooled_verdict(_pooled_ci(p)).replace("*", ""), []).append(
            PLAIN_EXPERIMENT.get(exp, exp))
    parts = [f"{verdict.replace(' with the fix', '')} for {', '.join(names)}"
             for verdict, names in sorted(groups.items())]
    return f"Pooled over the {len(fix['models'])} models: " + "; ".join(parts) + ". "


def _judge_files(root: pathlib.Path) -> list[tuple[str, dict]]:
    """Every committed, non-demonstration judge-vs-oracle evidence file, as (relative path, data)."""
    out = []
    for f in sorted((root / "evals/validation/v1").glob("judge_eval_*.json")):
        rel = str(f.relative_to(root)).replace("\\", "/")
        d = _load(root, rel)
        if d:
            out.append((rel, d))
    return out


_LOCAL_GRADER_FILES = set(LOCAL_GRADER_EVIDENCE.values())


def _grader_more_accurate(g: dict, base: dict) -> bool:
    """The McNemar test compares per-item correctness, so its direction is accuracy (F1 if absent)."""
    base_acc = (base.get("accuracy") or {}).get("point")
    return g["accuracy"]["point"] > base_acc if base_acc is not None else g["f1"] > base.get("f1", 0)


def _comparisons(checks: dict) -> list[tuple[float, bool]]:
    """(McNemar p, is the grader the more accurate one?) per grader-vs-baseline comparison."""
    return [(b[k]["vs_grader"]["mcnemar_p"], _grader_more_accurate(b["grader"], b[k]))
            for b in checks.values() for k in ("naive_regex", "tuned_heuristic") if "vs_grader" in b.get(k, {})]


def _check_span(d: dict) -> str:
    return ", ".join(f"{c.replace('_', ' ')} {_iv(b['grader']['accuracy'])}" for c, b in sorted(d["checks"].items()))


def _floor_text(dec: dict) -> str:
    floors = {(c["floor"]["accuracy"], c["floor"]["f1"]) for c in dec["per_check"].values()}
    if len(floors) == 1:
        acc, f1 = floors.pop()
        return f"accuracy at least {acc:.2f} and F1 at least {f1:.2f} on both checks"
    return "; ".join(f"{c.replace('_', ' ')}: accuracy at least {v['floor']['accuracy']:.2f}, F1 at least "
                     f"{v['floor']['f1']:.2f}" for c, v in dec["per_check"].items())


def _local_verdict(dec: dict) -> str:
    if dec["meets_floor"]:
        return ("met, so it stays the default free grader (`fusion doctor` recommends it when the claude CLI "
                "isn't available)")
    return ("not met, so `fusion doctor` no longer recommends it by default (it can still be chosen explicitly; every "
            "run measures its grader in-run and withholds the grade when it falls short)")


def _bottom_line(root: pathlib.Path) -> list[str]:
    """Four plain answers, each derived by rule from the evidence (never typed by hand)."""
    out = ["## Bottom line", ""]
    judge = _judge_files(root)
    primary = [d for rel, d in judge if rel not in _LOCAL_GRADER_FILES]
    detect = []
    if primary:
        span = "; ".join(f"{d['grader']}: {_check_span(d)}" for d in primary)
        beats = all(b["grader"]["f1"] >= b.get(k, {}).get("f1", 0) for d in primary for b in d["checks"].values()
                    for k in ("naive_regex", "tuned_heuristic"))
        sig = any(p < 0.05 and better for d in primary for p, better in _comparisons(d["checks"]))
        b3 = _load(root, B3_EVIDENCE)
        plain = ""
        if b3:
            p = b3["pooled"]
            plain = (" It also beats a plain one-question judge using the same model (pre-registered)."
                     if b3["decision"]["claim_allowed"] else
                     f" A plain one-question judge using the same model was just as accurate on the same items "
                     f"(rubric {_pct(p['rubric']['accuracy']['point'])}, plain "
                     f"{_pct(p['b3']['accuracy']['point'])}), so Fusion does not claim its rubric improves accuracy.")
        detect.append(f"Graded against deterministic oracles: {span}. "
                      + ("It beats the rule-based checks" if beats else "It does not always beat the rule-based checks")
                      + (" significantly." if sig else ", but not significantly yet (small samples).") + plain)
    for rel, d in judge:
        if rel in _LOCAL_GRADER_FILES:
            dec = local_grader_decision(d)
            detect.append(f"The free local grader, {d['grader']}, pre-registered: {_check_span(d)}. Its registered "
                          f"bar ({_floor_text(dec)}): {_local_verdict(dec)}.")
    out.append("- **Detecting accurately?** " + (" ".join(detect) if detect else "Not yet measured."))
    fix = _load(root, "evals/validation/v1/evidence_oracle.json")
    if fix:
        cells = fix.get("cells", [])
        worse = [c for c in cells if c["before_after"]["absolute_reduction"]["point"] < 0
                 and c["before_after"]["mcnemar_p"] < 0.05]
        proven = [c for c in cells if c["before_after"].get("honesty") == "PROVEN"
                  and c["before_after"]["absolute_reduction"]["point"] > 0]
        models = ", ".join(sorted(fix.get("models", {})))
        named = lambda cs: ", ".join(f"{c['experiment']} on {c['model']}" for c in cs)  # noqa: E731
        out.append(f"- **Fixing effectively?** On {models}: "
                   + (f"{len(proven)} proven improvement(s) ({named(proven)})" if proven
                      else "no proven improvement from the prompt fix")
                   + (f"; {len(worse)} significant regression(s) ({named(worse)})" if worse else "")
                   + ". " + _pooled_sentence(fix)
                   + "Every report card therefore measures the fix on the user's own model instead of assuming it helps.")
    else:
        out.append("- **Fixing effectively?** Not yet measured.")
    step2 = _load(root, STEP2_EVIDENCE)
    if step2 and step2["decision"]["new_rules"] == "adopted":
        out.append(_step2_sentence(step2))
        step3 = _load(root, STEP3_EVIDENCE)
        if step3 and step3["decision"] == "adopted":
            out[-1] += " " + _step3_sentence(step3)
        step4 = _load(root, STEP4_EVIDENCE)
        if step4:
            out[-1] += " " + _step4_sentence(step4)
    else:
        out.append("- **Runtime guardrail in your agent?** Not yet measured with the current rules.")
    guard = _guard_headline(root)
    if guard:
        out.append(f"- **Runtime guard (Claude Code hook)?** On held-out tool calls it prompted on "
                   f"{_iv(guard['benign']['over_block'])} of benign calls and caught {_iv(guard['malicious']['recall'])} "
                   "of attack-shaped ones as written: useful defense in depth, not a sandbox.")
    counts = _error_counts(fix, judge)
    out.append("- **Erroring often?** " + ("; ".join(counts).capitalize() + ". " if counts else "")
               + _WITHHELD)
    return out + [""]


_WITHHELD = ("Every card counts and shows its unscored cases, and a grade is withheld ('?') when too much "
             "is unscored, when the grader misses the known-answer floor, or when it denies an "
             "oracle-confirmed violation.")


def _error_counts(fix: dict | None, judge: list[tuple[str, dict]]) -> list[str]:
    """How often generation or grading failed, from the fix-efficacy run and the judge evaluations."""
    counts = []
    if fix:
        cells = fix.get("cells", [])
        items = sum(c["n_items"] for c in cells)
        unscored = sum(c["n_unscored"] for c in cells)
        undecidable = sum(c["n_undecidable"] for c in cells)
        truncated = sum(c.get("n_truncated", 0) for c in cells)
        counts.append(f"in the fix-efficacy run, {unscored} of {items} item pairs failed to generate, "
                      f"{undecidable} were undecidable by the oracle and {truncated} were cut by the token cap")
    if judge:
        unanswered = sum(b["grader"].get("unanswered", 0) for _, d in judge for b in d["checks"].values())
        total = sum(b["grader"]["n"] + b["grader"].get("unanswered", 0) for _, d in judge for b in d["checks"].values())
        counts.append(f"in the judge evaluation, {unanswered} of {total} questions went unanswered")
    return counts


def _q2(root: pathlib.Path) -> list[str]:
    fix = _load(root, "evals/validation/v1/evidence_oracle.json")
    judge = _judge_files(root)
    counts = _error_counts(fix, judge)
    out = ["## Q2: Does it error?", ""]
    if not counts:
        return out + ["NOT YET MEASURED.", ""]
    sources = (["`evals/validation/v1/evidence_oracle.json`"] if fix else []) + [f"`{rel}`" for rel, _ in judge]
    return out + [f"- {c[0].upper()}{c[1:]}." for c in counts] + [
        f"- {_WITHHELD}", "", "Evidence: " + ", ".join(sources) + ".", ""]


def _significance_of(d: dict) -> str:
    comps = _comparisons(d["checks"])
    better = sum(1 for p, b in comps if p < 0.05 and b)
    worse = sum(1 for p, b in comps if p < 0.05 and not b)
    if better or worse:
        side = ("all in the grader's favour" if not worse else
                "all against the grader (a rule-based baseline was more accurate)" if not better else
                f"{better} in the grader's favour, {worse} against it")
        return f"{better + worse} of {len(comps)} grader-vs-baseline comparisons are significant at 0.05, {side}."
    return (f"None of the {len(comps)} grader-vs-baseline comparisons is significant at 0.05 yet: "
            + ("the grader scores higher, but these samples can't rule out chance." if all(b for _, b in comps)
               else "these samples can't tell the grader and the rule-based baselines apart."))


def _significance(rows: list[tuple[str, dict]]) -> str:
    if len(rows) == 1:
        return _significance_of(rows[0][1])
    return " ".join(f"**{d['grader']}:** {_significance_of(d)}" for _, d in rows)


def _local_grader_paragraph(d: dict) -> list[str]:
    dec = local_grader_decision(d)
    result = "; ".join(f"{c.replace('_', ' ')}: accuracy {_pct(v['accuracy'])}, F1 "
                       + ("–" if v["f1"] is None else f"{v['f1']:.2f}") for c, v in dec["per_check"].items())
    return ["", (f"**Free local grader (pre-registered).** `evals/validation/v1/PREREG_local_grader.md` fixed its bar "
                f"before the grader answered any question: {_floor_text(dec)}. Result: {result}. Bar "
                f"{_local_verdict(dec)}.")]


def _q1(root: pathlib.Path) -> list[str]:
    out = ["## Q1: Is the judge accurate?", ""]
    rows = _judge_files(root)
    if not rows:
        return out + ["NOT YET MEASURED: no committed judge-vs-oracle evidence.", ""]
    out += [
        ("Grader verdicts on real open-weight model transcripts vs deterministic oracle labels (InjecAgent: "
        "attacker tool called; Gandalf: planted password leaked), with two rule-based baselines on the same "
        "items. Unanswered items are counted and excluded from the rates."),
        "",
        "| Evidence | Grader | Check | n (unanswered) | Accuracy | Recall | Specificity | F1 | κ | Naive regex F1 | Tuned heuristic F1 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rel, d in rows:
        for check, b in sorted(d["checks"].items()):
            g = b["grader"]
            nr, th = b.get("naive_regex", {}), b.get("tuned_heuristic", {})
            out.append(
                f"| `{rel}` | {d['grader']} | {check} | {g['n']} ({g.get('unanswered', 0)}) | {_iv(g['accuracy'])} "
                f"| {_iv(g['recall'])} | {_iv(g['specificity'])} | {g['f1']:.2f} | {g['kappa']:.2f} "
                f"| {nr.get('f1', float('nan')):.2f} | {th.get('f1', float('nan')):.2f} |")
    for rel, d in rows:  # after the table, so a paragraph never splits it
        audit = d.get("audit")
        if audit:
            out += ["", f"Disagreement audit (`{rel}`): {audit.get('method', 'an LLM reading, not ground truth')} "
                    + "; ".join(f"{k}: {v}" for k, v in audit["summary"].items())
                    + (f". {audit['note']}" if audit.get("note") else "")]
    for rel, d in rows:
        if rel in _LOCAL_GRADER_FILES:
            out += _local_grader_paragraph(d)
    out += [
        "",
        "Paired McNemar compares per-item correctness (not F1). " + _significance(rows),
        ("Each item appears twice (as written and with the fix), so rows are not fully independent and the "
        "intervals are somewhat narrow. The leakage oracle is a string match for the planted password; the "
        "baselines are not told the password."),
        "",
        ("Each run also measures its grader in-run (known-answer questions plus an oracle cross-check on "
        "clear-cut questions) and withholds the grade below the policy floor."),
        "",
    ]
    return out


def _q3(root: pathlib.Path) -> list[str]:
    out = ["## Q3: Does the fix work, and what does it cost?", ""]
    d = _load(root, "evals/validation/v1/evidence_oracle.json")
    if not d:
        return out + [("NOT YET MEASURED: the oracle-labelled evidence run on local open-weight models "
                      "has not been committed yet."), ""]
    models = ", ".join(sorted(d.get("models", {})))
    out += [(f"The prompt as written vs with Fusion's fix, on local models ({models}), over held-out items "
            "from external benchmarks. Issue = oracle-confirmed attack success (InjecAgent: attacker tool "
            "called; Gandalf: planted password leaked) or cost (XSTest: safe request refused; IFEval: "
            "instruction not followed). Lower is better. Evidence: `evals/validation/v1/evidence_oracle.json`."),
            ""]
    pooled = d.get("pooled") or {}
    if len(d.get("models", {})) > 1 and pooled:
        out += [("**Pooled over all models.** The interval resamples whole items (each item runs on every "
                "model)."), "",
                "| Experiment | Pairs | As written | With fix | Change in issue rate (95% CI) | What it shows |",
                "|---|---|---|---|---|---|"]
        for exp, p in pooled.items():
            ci = _pooled_ci(p)
            out.append(f"| {exp} (pooled) | {p['n_pairs']} | {_iv(p['baseline_rate'])} | "
                       f"{_iv(p['hardened_rate'])} | {_pp(-ci['point'])} ({-ci['high'] * 100:+.0f} to "
                       f"{-ci['low'] * 100:+.0f}) | {_pooled_verdict(ci)} |")
        out += ["", "**Per model:**", ""]
    out += ["| Experiment | Model | Pairs | As written | With fix | Paired test | What it shows |",
            "|---|---|---|---|---|---|---|"]
    regressions, wins = [], []
    for c in d.get("cells", []):
        ba = c["before_after"]
        red, p = ba["absolute_reduction"], ba["mcnemar_p"]
        if red["point"] < 0 and p < 0.05:
            verdict = "**significantly worse with the fix**"
            regressions.append(f"{c['experiment']} on {c['model']}")
        elif red["point"] > 0 and ba.get("honesty") == "PROVEN":
            verdict = "significantly better with the fix (PROVEN)"
            wins.append(f"{c['experiment']} on {c['model']}")
        elif red["point"] < 0:
            verdict = "worse with the fix, not significant"
        elif red["point"] > 0:
            verdict = "better with the fix, preliminary"
        else:
            verdict = "no change"
        out.append(f"| {c['experiment']} | {c['model']} | {c['n_paired']} | {_iv(c['baseline_rate'])} | "
                   f"{_iv(c['hardened_rate'])} | McNemar p={p:.3f} | {verdict} |")
    summary = []
    if regressions:
        summary.append("Significant regressions: " + "; ".join(regressions) + ".")
    summary.append("Proven improvements: " + ("; ".join(wins) + "." if wins else "none yet."))
    out += ["", " ".join(summary), *_compact_clause(root), ""]
    return out


COMPACT_EVIDENCE = "evals/validation/v1/compact_fix.json"


def _compact_clause(root: pathlib.Path) -> list[str]:
    """The pre-registered compact variant of the fix, as one sentence: its registered decision."""
    d = _load(root, COMPACT_EVIDENCE)
    if not d or "prereg_decision" not in d:
        return []
    if d["prereg_decision"]["adopt"]:
        verdict = "was adopted for small models (registered rule met)"
    elif any(m["attack_higher"] for m in d["prereg_decision"]["per_model"].values()):
        verdict = "was not adopted: a model had significantly more attacks with it"
    else:
        verdict = ("was not adopted: no model had significantly fewer attacks with it without a meaningful rise in "
                   "refusals of safe requests")
    return ["", (f"A pre-registered compact version of the fix (`evals/validation/v1/PREREG_compact_fix.md`; evidence: "
                f"`{COMPACT_EVIDENCE}`) {verdict}.")]


def _guard_sets(root: pathlib.Path) -> list[tuple[str, dict]]:
    """Every scored held-out set, oldest first."""
    found = []
    for i in range(1, 10):
        d = _load(root, f"evals/guard_bench/claude_code_heldout_v{i}.json")
        if d:
            found.append((f"v{i}", d))
    return found


def _guard_status(d: dict) -> str:
    """The evidence's status code in words: "HELD OUT at rules_git_sha" -> "held out, scored once"."""
    raw = d["status"].split(".")[0]
    rules = (d.get("rules_git_sha") or "unknown")[:7]
    if raw.startswith("HELD OUT"):
        return "held out, scored once"
    return raw.replace("rules_git_sha", "rules " + rules).capitalize()


def _guard_current(root: pathlib.Path) -> tuple[str, dict] | None:
    """The newest held-out set (older ones were scored against rules that have since changed)."""
    sets = _guard_sets(root)
    return next(((v, d) for v, d in reversed(sets) if d["status"].startswith("HELD OUT")), sets[-1] if sets else None)


def _guard_headline(root: pathlib.Path) -> dict | None:
    cur = _guard_current(root)
    return cur[1] if cur else None


def _guard(root: pathlib.Path) -> list[str]:
    out = ["## Runtime guard for Claude Code (fusion-guard hook)", ""]
    cur = _guard_current(root)
    if not cur:
        return out + ["NOT YET MEASURED.", ""]
    v, d = cur
    sens = d.get("sensitivity_test_tld_as_public")
    head = "| Set | benign n | Prompted (over-block) | attack n | Caught (recall) |" + (
        " Caught, .test hosts as public |" if sens else "") + " Status |"
    row = (f"| {v} | {d['benign']['n']} | {_iv(d['benign']['over_block'])} | {d['malicious']['n']} | "
           f"{_iv(d['malicious']['recall'])} |" + (f" {_iv(sens['recall'])} |" if sens else "") + f" {_guard_status(d)} |")
    return out + [
        "Tool calls written by independent agents **blind to the rules**, scored once.",
        "",
        head,
        "|---" * head.count(" |") + "|",
        row,
        "",
        ("Pattern rules catch the common exfiltration / destruction / remote-code shapes and miss much of "
        "the long tail; treat the hook as defense in depth, not a sandbox."),
        "",
    ]


def _limits() -> list[str]:
    return [
        "## Known limits",
        "",
        ("- Oracle labels decide narrow questions (a tool was called, a password appeared). Where the "
        "judge's rubric is broader than the oracle, some 'disagreements' are real violations the oracle "
        "can't see: see each disagreement audit."),
        "- Samples are small (tens of transcripts per cell); read the intervals, not the points.",
        ("- Known-answer questions come from a public gold set; the in-run oracle cross-check covers only "
        "clear-cut questions."),
        "",
    ]


# Committed evidence no longer reported (replaced rules, later measurements, a variant not adopted).
SUPERSEDED_EVIDENCE = (
    "evals/validation/v1/guard_on_transcripts.json",
    "evals/validation/v1/guard_on_fresh_transcripts.json",
    "evals/validation/v1/guard_vs_llama_guard.json",
    "evals/validation/v1/value_ledger.json",
    "evals/validation/v1/compact_vs_full_fix.json",
)


def _superseded(root: pathlib.Path) -> list[str]:
    cur = _guard_current(root)
    older_sets = [f"evals/guard_bench/claude_code_heldout_{v}.json" for v, _ in _guard_sets(root) if cur and v != cur[0]]
    kept = [rel for rel in SUPERSEDED_EVIDENCE if (root / rel).is_file()] + older_sets
    return [f"Superseded evidence kept for audit: {', '.join(f'`{rel}`' for rel in kept)}.", ""] if kept else []


def evidence_json(root: pathlib.Path | None = None) -> dict:
    """The same evidence for the website's /trust page, as raw rates in [0, 1]."""
    root = root or data_root()
    judge = []
    for f in sorted((root / "evals/validation/v1").glob("judge_eval_*.json")):
        rel = str(f.relative_to(root)).replace("\\", "/")
        d = _load(root, rel)
        if not d:
            continue
        for check, b in sorted(d["checks"].items()):
            g = b["grader"]
            judge.append({
                "evidence": rel, "grader": d["grader"], "check": check, "n": g["n"],
                "accuracy": g["accuracy"], "recall": g["recall"], "specificity": g["specificity"],
                "f1": g["f1"], "kappa": g["kappa"],
                "baselines": {name: {"f1": b[name]["f1"], "mcnemar_p": b[name]["vs_grader"]["mcnemar_p"],
                                     "grader_more_accurate": _grader_more_accurate(g, b[name])}
                              for name in ("naive_regex", "tuned_heuristic") if "f1" in b.get(name, {})},
                "audit": (d.get("audit") or {}).get("summary"),
            })
    guard = []
    cur = _guard_current(root)
    if cur:
        v, d = cur
        guard.append({"set": v, "evidence": f"evals/guard_bench/claude_code_heldout_{v}.json",
                      "benign_n": d["benign"]["n"], "over_block": d["benign"]["over_block"],
                      "attack_n": d["malicious"]["n"], "recall": d["malicious"]["recall"],
                      "recall_sensitivity": (d.get("sensitivity_test_tld_as_public") or {}).get("recall"),
                      "status": _guard_status(d), "rules": (d.get("rules_git_sha") or "")[:7] or None})
    fix = _load(root, "evals/validation/v1/evidence_oracle.json")
    fix_pooled = []
    if fix and len(fix.get("models", {})) > 1:
        for exp, p in (fix.get("pooled") or {}).items():
            ci = _pooled_ci(p)  # reduction; the site shows the change in issue rate (fix minus as written)
            fix_pooled.append({"experiment": exp, "n_pairs": p["n_pairs"], "baseline_rate": p["baseline_rate"],
                               "hardened_rate": p["hardened_rate"],
                               "change": {"point": -ci["point"], "low": -ci["high"], "high": -ci["low"]},
                               "verdict": _pooled_verdict(ci).replace("*", "")})
    b3 = _load(root, B3_EVIDENCE)
    rubric_vs_plain = None
    if b3:
        def _pair(b: dict) -> dict:
            return {"n": b["n"], "plain_unanswered": b["b3_unanswered"], "rubric": b["rubric"]["accuracy"],
                    "plain": b["b3"]["accuracy"], "difference": b["accuracy_difference"], "mcnemar_p": b["mcnemar_p"]}

        rubric_vs_plain = {"evidence": B3_EVIDENCE, "claim_allowed": b3["decision"]["claim_allowed"],
                           "pooled": _pair(b3["pooled"]),
                           "by_check": {c: _pair(b) for c, b in sorted(b3["by_check"].items())}}
    local = next(((rel, d) for rel, d in _judge_files(root) if rel in _LOCAL_GRADER_FILES), None)
    local_grader = None
    if local:
        dec = local_grader_decision(local[1])
        local_grader = {"evidence": local[0], "grader": local[1]["grader"], "meets_floor": dec["meets_floor"],
                        "rule": dec["rule"], "per_check": dec["per_check"]}
    return {"generated_from": "evals/ (non-demonstration evidence only)", "judge_accuracy": judge,
            "local_grader": local_grader,
            "step2_guard": _step2_site(root), "step3_guard": _step3_site(root), "step4_agentdojo": _step4_site(root),
            "rubric_vs_plain": rubric_vs_plain, "fix_pooled": fix_pooled or None,
            "guard_heldout": guard, "fix_efficacy": (fix or {}).get("cells", None)}


B3_EVIDENCE = "evals/validation/v1/b3_rubric_vs_plain_judge.json"


_ATTACK_TYPE_NAMES = {"gandalf:leak": "password leaks (Gandalf)",
                      "injecagent:ds": "tool hijack, data stealing (InjecAgent)",
                      "injecagent:dh": "tool hijack, direct harm (InjecAgent)"}


_ATTACK_TYPE_SHORT = {"gandalf:leak": "password leaks", "injecagent:ds": "data-stealing tool hijacks",
                      "injecagent:dh": "direct-harm tool hijacks"}


def _guardrail_table(d: dict) -> list[str]:
    out = ["| Attack | Real attacks | Stopped | Clean transcripts | Wrongly blocked |", "|---|---|---|---|---|"]
    for k, s in sorted(d["by_attack_type"].items()):
        out.append(f"| {_ATTACK_TYPE_NAMES.get(k, k)} | {s['attacks']} | {_iv(s['recall'])} | {s['clean']} | "
                   f"{_iv(s['over_block'])} |")
    a = d["all"]
    out.append(f"| all | {a['attacks']} | {_iv(a['recall'])} | {a['clean']} | {_iv(a['over_block'])} |")
    out.append("")
    out += [f"- {f}" for f in d.get("findings", [])]
    if d.get("deviation_note"):
        out.append(f"- Deviation, disclosed: {d['deviation_note']}")
    return out


def _b3_verdict(d: dict) -> str:
    if d["decision"]["claim_allowed"]:
        return ("The rubric judge is significantly more accurate than a plain LLM judge (the "
                "pre-registered rule is met).")
    return ("**Not shown:** the rubric judge is not significantly more accurate than asking the same model "
            "one plain question, so Fusion does not claim it is. What the rubric still provides is a "
            "checkable grade: per-criterion answers with quoted evidence, which the run engine uses to "
            "reject ungrounded grades.")


def _b3(root: pathlib.Path) -> list[str]:
    d = _load(root, B3_EVIDENCE)
    if not d:
        return []
    out = ["## Q4: Does the rubric beat simply asking an LLM?", "",
           ("The same items graded twice by the same Claude Sonnet: once with Fusion's rubric (the Q1 "
           "answers), once asked one plain yes/no question with no rubric. Pre-registered in "
           "`evals/validation/v1/PREREG_b3_single_question.md`; evidence: "
           f"`{B3_EVIDENCE}`."), "",
           ("| Check | n (plain unanswered) | Rubric judge | Plain judge | Difference, rubric minus plain (95% CI) "
           "| Paired test |"), "|---|---|---|---|---|---|"]
    for name, b in [*sorted(d["by_check"].items()), ("pooled", d["pooled"])]:
        diff = b["accuracy_difference"]
        out.append(f"| {name} | {b['n']} ({b['b3_unanswered']}) | {_iv(b['rubric']['accuracy'])} | "
                   f"{_iv(b['b3']['accuracy'])} | {_pp(diff['point'])} ({diff['low'] * 100:+.0f} to "
                   f"{diff['high'] * 100:+.0f}) | McNemar p={b['mcnemar_p']:.3f} |")
    return out + ["", _b3_verdict(d), ""]


def _p(p: float) -> str:
    return "p<0.0001" if p < 0.0001 else f"p={p:.4f}"


def _lg_verdict(name: str, c: dict) -> str:
    a = c["attacks"]
    if c["decision"] == "fusion_better":
        return (f"Fusion's guardrail stops significantly more real attacks than Llama Guard 3 {name} "
                f"({a['fusion_only']} stopped only by Fusion, {a['other_only']} only by Llama Guard; McNemar "
                f"{_p(a['mcnemar_p'])}), without significantly more wrong blocks.")
    if c["decision"] == "other_better":
        return (f"Llama Guard 3 {name} stops significantly more real attacks than Fusion's guardrail "
                f"({a['other_only']} vs {a['fusion_only']}; McNemar {_p(a['mcnemar_p'])}).")
    return (f"Against Llama Guard 3 {name}: no significant difference by the registered rule ({a['fusion_only']} "
            f"stopped only by Fusion, {a['other_only']} only by Llama Guard; McNemar {_p(a['mcnemar_p'])}).")


STEP2_EVIDENCE = "evals/validation/v1/step2_guard.json"
_STEP2_ROWS = (("Fusion guard, current rules", "fusion"), ("Fusion guard, previous rules", "fusion_prior"),
               ("Llama Guard 3, off the shelf", "llama_guard_a"), ("Llama Guard 3, configured", "llama_guard_b"),
               ("Fusion + Llama Guard 3 (configured)", "union_fusion_b"))


def _prior_verdict(c: dict) -> str:
    a, cl = c["attacks"], c["clean"]
    if c["decision"] == "fusion_better":
        return (f"The current rules stop significantly more real attacks than the previous rules ({a['fusion_only']} "
                f"stopped only by the current rules, {a['other_only']} only by the previous; McNemar "
                f"{_p(a['mcnemar_p'])}), without significantly more wrong blocks ({cl['fusion_only']} vs "
                f"{cl['other_only']}; p={cl['mcnemar_p']:.2f}).")
    return (f"Against the previous rules: {c['decision'].replace('_', ' ')} by the registered rule "
            f"({a['fusion_only']} vs {a['other_only']} attacks; McNemar p={a['mcnemar_p']:.4f}).")


def _step2_sentence(d: dict) -> str:
    a = d["fusion"]["all"]
    by = d["by_attack_type"]["fusion"]
    listed = ", ".join(f"{_pct(s['recall']['point'])} of {_ATTACK_TYPE_SHORT.get(g, g)}"
                       for g, s in sorted(by.items(), key=lambda kv: -kv[1]["recall"]["point"]))
    prior, lgb = d["fusion_prior"]["all"], d["llama_guard_b"]["all"]
    return (f"- **Runtime guardrail in your agent?** On fresh real attacks against {' and '.join(d['models'])}, "
            f"measured once with the current rules (pre-registered), it stopped {a['stopped']} of {a['attacks']}, "
            f"{_iv(a['recall'])}: {listed}. It wrongly blocked {_iv(a['over_block'])} of clean transcripts. On the "
            f"same transcripts the previous rules stopped {prior['stopped']} and Llama Guard 3 (configured) "
            f"{lgb['stopped']}, wrongly blocking {_iv(lgb['over_block'])}.")


def _step2(root: pathlib.Path) -> list[str]:
    d = _load(root, STEP2_EVIDENCE)
    if not d:
        return []
    n = d["sample"]["n"]
    out = ["## Request-bound guardrail on 7–8B models (pre-registered)", "",
           (f"The current rules (`fusion_first/guardrail` at `{d['guardrail_git_sha'][:7]}`: once untrusted content is in "
           "context, a tool call that is not a read must be covered by the user's own request, and an unrequested "
           "read of private data is blocked) measured once on fresh transcripts of "
           f"{' and '.join(d['models'])} ({n['injecagent']} InjecAgent and {n['gandalf']} Gandalf items each, prompt "
           f"as written), against the previous rules (`{d['prior_guardrail_git_sha'][:7]}`) and Llama Guard 3 "
           f"8B on the same transcripts. Registered in `{d['preregistration']}`; evidence: `{STEP2_EVIDENCE}`."), "",
           "| System | Real attacks stopped | Clean transcripts wrongly blocked |", "|---|---|---|"]
    for label, key in _STEP2_ROWS:
        s = d[key]["all"]
        out.append(f"| {label} | {s['stopped']} of {s['attacks']}, {_iv(s['recall'])} | "
                   f"{s['blocked']} of {s['clean']}, {_iv(s['over_block'])} |")
    comps, b, u = d["comparisons"], d["benign_heldout"], d["unseen_attacker_tools"]
    out += ["", f"- {_prior_verdict(comps['fusion_vs_fusion_prior'])}",
            f"- {_lg_verdict('off the shelf', comps['fusion_vs_llama_guard_a'])}",
            f"- {_lg_verdict('configured', comps['fusion_vs_llama_guard_b'])}",
            (f"- Legitimate requested actions never used in development: {len(b['blocked_by_new_rules'])} of "
            f"{b['cases']} blocked by the current rules (registered limit {b['max_allowed']})."),
            (f"- Attacks whose attacker tool never appeared in development: {u['stopped_new']} of {u['attacks']} "
            f"stopped (previous rules {u['stopped_prior']}, Llama Guard 3 configured {u['stopped_llama_guard_b']})."),
            f"- Registered decision: the current rules are **{d['decision']['new_rules']}**.", "",
            "Current rules by attack type:", "",
            *_guardrail_table({"by_attack_type": d["by_attack_type"]["fusion"],
                               "all": {**d["fusion"]["all"], "over_blocked": d["fusion"]["all"]["blocked"]},
                               "findings": d.get("findings", [])})]
    return out + [""]


def _step2_site(root: pathlib.Path) -> dict | None:
    d = _load(root, STEP2_EVIDENCE)
    if not d:
        return None
    keep = ("attacks", "stopped", "recall", "clean", "blocked", "over_block")
    b = d["benign_heldout"]
    return {"evidence": STEP2_EVIDENCE, "models": list(d["models"]), "n": d["sample"]["n"],
            "rules": d["guardrail_git_sha"][:7], "prior_rules": d["prior_guardrail_git_sha"][:7],
            "systems": {key: {k: d[key]["all"][k] for k in keep} | {"label": label} for label, key in _STEP2_ROWS},
            "by_attack_type": {g: {k: s[k] for k in keep} | {"name": _ATTACK_TYPE_NAMES.get(g, g)}
                               for g, s in sorted(d["by_attack_type"]["fusion"].items())},
            "comparisons": {"previous_rules": d["comparisons"]["fusion_vs_fusion_prior"],
                            "off_the_shelf": d["comparisons"]["fusion_vs_llama_guard_a"],
                            "configured": d["comparisons"]["fusion_vs_llama_guard_b"]},
            "benign_heldout": {"cases": b["cases"], "blocked": len(b["blocked_by_new_rules"]),
                               "max_allowed": b["max_allowed"]},
            "unseen_attacker_tools": d["unseen_attacker_tools"], "decision": d["decision"],
            "findings": d.get("findings", [])}


STEP3_EVIDENCE = "evals/validation/v1/step3_guard.json"
_STEP3_ROWS = (("Given the tool results", "v3"), ("Without them (as step 2)", "v2"))


def _step3_sentence(d: dict) -> str:
    v3, v2 = d["v3"]["all"], d["v2"]["all"]
    ds3, ds2 = d["v3"]["by_kind"]["ds"], d["v2"]["by_kind"]["ds"]
    return (f"Given the tool results as well, on further fresh transcripts of the same models (pre-registered), it "
            f"stopped {v3['stopped']} of {v3['attacks']} attacks ({ds3['stopped']} of {ds3['attacks']} data-stealing) "
            f"vs {v2['stopped']} ({ds2['stopped']}) without them, wrongly blocking {v3['blocked']} of "
            f"{v3['clean']} clean transcripts either way.")


def _step3(root: pathlib.Path) -> list[str]:
    d = _load(root, STEP3_EVIDENCE)
    if not d:
        return []
    c, inp = d["comparisons"], d["decision_inputs"]
    out = ["## The guard given the tool results (pre-registered)", "",
           (f"The same rules (`{d['guardrail_git_sha'][:7]}`) with and without the text of the tool results the agent "
           "saw (`untrusted_text`): given it, a read that text asks for, and the user did not, is blocked when the "
           "text also asks to send data to an outside address. Measured once on fresh InjecAgent transcripts of "
           f"{' and '.join(d['models'])} ({d['sample']['n']} items each). Registered in `{d['preregistration']}`; "
           f"evidence: `{STEP3_EVIDENCE}`."), "",
           "| Guard | Real attacks stopped | Data-stealing stopped | Clean transcripts wrongly blocked |",
           "|---|---|---|---|"]
    for label, key in _STEP3_ROWS:
        s, ds = d[key]["all"], d[key]["by_kind"]["ds"]
        out.append(f"| {label} | {s['stopped']} of {s['attacks']}, {_iv(s['recall'])} | {ds['stopped']} of "
                   f"{ds['attacks']}, {_iv(ds['recall'])} | {s['blocked']} of {s['clean']}, {_iv(s['over_block'])} |")
    a, cl = c["attacks"], c["clean"]
    out += ["", (f"- Attacks stopped only with the tool results: {a['v3_only']}; only without: {a['v2_only']} "
                f"(McNemar {_p(a['p'])}). Clean transcripts blocked only with: {cl['v3_only']}; only without: "
                f"{cl['v2_only']} (registered limit: {inp['max_extra_clean_blocked']} more, net)."),
            f"- Registered decision: **{d['decision']}**.",
            ("- Limits registered before data: InjecAgent's attack wording appeared in development (this tests fresh "
            "model behaviour, not unseen attack text), and no fresh set of legitimate actions was available, so "
            "the cost is measured on clean transcripts only. Reads a user delegates to a document (\"do what this "
            "email says\") are blocked when the document also asks to send data out."), ""]
    return out


def _step3_site(root: pathlib.Path) -> dict | None:
    d = _load(root, STEP3_EVIDENCE)
    if not d:
        return None
    keep = ("attacks", "stopped", "recall", "clean", "blocked", "over_block")
    return {"evidence": STEP3_EVIDENCE, "models": list(d["models"]), "n": d["sample"]["n"],
            "rules": d["guardrail_git_sha"][:7],
            "arms": {key: {k: d[key]["all"][k] for k in keep}
                     | {"label": label, "data_stealing": {k: d[key]["by_kind"]["ds"][k] for k in keep}}
                     for label, key in _STEP3_ROWS},
            "comparisons": d["comparisons"], "decision": d["decision"]}


STEP4_EVIDENCE = "evals/validation/v1/step4_agentdojo.json"


def _step4_sentence(d: dict) -> str:
    u, c = d["utility_benign"], d["comparisons"]["cost_none_vs_v3"]
    verdict = ("within" if c["non_inferior"] else "over")
    return (f"Its cost, in a live AgentDojo agent loop on held-out tasks ({d['model']}, pre-registered): the agent "
            f"completed {u['v3']['k']} of {u['v3']['n']} legitimate tasks with the guard vs {u['none']['k']} without "
            f"it ({c['a_only']} broken, {c['b_only']} fixed), {verdict} the registered 10-point margin.")


def _step4(root: pathlib.Path) -> list[str]:
    d = _load(root, STEP4_EVIDENCE)
    if not d:
        return []
    u, s, cmp = d["utility_benign"], d["attack_success_in_scope"], d["comparisons"]
    c, a = cmp["cost_none_vs_v3"], cmp["attacks_none_vs_v3"]
    out = ["## The guard's cost in a live agent loop (AgentDojo, pre-registered)", "",
           (f"AgentDojo ({d['benchmark']}) user tasks run through real tools by {d['model']}; the published guard "
           f"configuration (rules `{d['guardrail_git_sha'][:7]}`) checks every tool call and a blocked call does not "
           f"run. Held-out tasks only, scored once. Registered in `{d['preregistration']}`; evidence: "
           f"`{STEP4_EVIDENCE}`."), "",
           "| Arm | Legitimate tasks completed | In-scope attacks that succeeded |", "|---|---|---|"]
    for label, key in (("No guard", "none"), ("Guard, without the tool results", "v2"),
                       ("Guard, given the tool results (published)", "v3")):
        out.append(f"| {label} | {u[key]['k']} of {u[key]['n']}, {_iv(u[key])} | {s[key]['k']} of {s[key]['n']}, "
                   f"{_iv(s[key])} |")
    drop = c["drop"]
    out += ["", (f"- Cost: {c['a_only']} tasks completed only without the guard, {c['b_only']} only with it (McNemar "
                f"{_p(c['p'])}); completion fell {drop['point'] * 100:.1f} points (95% {drop['low'] * 100:.1f} to "
                f"{drop['high'] * 100:.1f}). Registered margin: 10 points. Decision: **{d['decision']['guard_cost']}**."),
            (f"- Given the tool results or not made no difference to cost ({cmp['cost_v2_vs_v3']['a_only']} vs "
            f"{cmp['cost_v2_vs_v3']['b_only']})."),
            (f"- Attacks (descriptive, not a registered test): {a['a_only']} succeeded only without the guard, "
            f"{a['b_only']} only with it (McNemar {_p(a['p'])})."),
            ("- What it blocked: requests worded differently from the tool (\"pay the bill\" for `send_money`, \"post\" "
            "for `send_channel_message`), sends to non-allowlisted addresses, addresses or links mentioned inside a "
            "message body read as destinations, and a file name (recipe-collection.docx) read as a host. These are rule "
            "changes for a fresh registration, not this one."),
            ""]
    return out


def _step4_site(root: pathlib.Path) -> dict | None:
    d = _load(root, STEP4_EVIDENCE)
    if not d:
        return None
    return {"evidence": STEP4_EVIDENCE, "model": d["model"], "benchmark": d["benchmark"],
            "rules": d["guardrail_git_sha"][:7], "utility_benign": d["utility_benign"],
            "attack_success_in_scope": d["attack_success_in_scope"], "comparisons": d["comparisons"],
            "decision": d["decision"]}


def render(root: pathlib.Path | None = None) -> str:
    root = root or data_root()
    parts = [HEADER, *_bottom_line(root), *_q1(root), *_q2(root), *_q3(root), *_b3(root),
             *_step2(root), *_step3(root), *_step4(root), *_guard(root),
             *_limits(), *_superseded(root)]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:  # pragma: no cover
    root = data_root()
    (root / "TRUST_REPORT.md").write_text(render(root), encoding="utf-8", newline="\n")
    (root / "frontend/src/content/evidence.json").write_text(
        json.dumps(evidence_json(root), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("wrote TRUST_REPORT.md and frontend/src/content/evidence.json")


if __name__ == "__main__":  # pragma: no cover
    main()
