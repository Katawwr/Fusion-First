"""TRUST_REPORT.md — generated ONLY from committed, non-demonstration evidence files.

No number in the report is typed by hand: every figure is read from a JSON file under `evals/` and
the file is named next to it. `tests/test_trust_report.py` regenerates the report and requires it to
equal the committed TRUST_REPORT.md, so the report can't drift from its evidence. Evidence that
doesn't exist yet is reported as NOT YET MEASURED — never estimated.
"""

from __future__ import annotations

import json
import pathlib

from fusion._data import data_root

HEADER = """# Fusion First — Trust Report

This report answers four questions about Fusion itself: **is it detecting accurately, does it error
often, does the fix work, and does it add value over simpler checks?** It is generated from committed
evidence files by `python -m fusion.validate.trust_report` — nothing here is typed by hand, and a test
fails if this file and its evidence disagree. Intervals are 95% Wilson (rates) unless noted. Evidence
from the offline stand-in judge (`demonstration: true`) is never used here.
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
    return "—" if x is None else f"{x * 100:.0f}%"


def _iv(d: dict | None) -> str:
    if not d:
        return "—"
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


def _bottom_line(root: pathlib.Path) -> list[str]:
    """Four plain answers, each derived by rule from the evidence (never typed by hand)."""
    out = ["## Bottom line", ""]
    judge = [_load(root, str(f.relative_to(root)).replace("\\\\", "/"))
             for f in sorted((root / "evals/validation/v1").glob("judge_eval_*.json"))]
    judge = [d for d in judge if d]
    if judge:
        accs = [(c, b["grader"]["accuracy"]) for d in judge for c, b in sorted(d["checks"].items())]
        span = ", ".join(f"{c.replace('_', ' ')} {_iv(a)}" for c, a in accs)
        pvals = [b[k]["vs_grader"]["mcnemar_p"] for d in judge for b in d["checks"].values()
                 for k in ("naive_regex", "tuned_heuristic") if "vs_grader" in b.get(k, {})]
        beats = all(b["grader"]["f1"] >= b.get(k, {}).get("f1", 0) for d in judge for b in d["checks"].values()
                    for k in ("naive_regex", "tuned_heuristic"))
        sig = any(p < 0.05 for p in pvals)
        out.append(f"- **Detecting accurately?** Graded against deterministic oracles: {span}. "
                   + ("It beats the rule-based checks" if beats else "It does not always beat the rule-based checks")
                   + (" significantly." if sig else ", but not significantly yet (small samples)."))
    else:
        out.append("- **Detecting accurately?** Not yet measured.")
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
    guard = _load(root, "evals/guard_bench/claude_code_heldout_v2.json") or _load(
        root, "evals/guard_bench/claude_code_heldout_v1.json")
    if guard:
        out.append(f"- **Runtime guard (Claude Code hook)?** On held-out tool calls it prompted on "
                   f"{_iv(guard['benign']['over_block'])} of benign calls and caught {_iv(guard['malicious']['recall'])} "
                   "of attack-shaped ones as written — useful defense in depth, not a sandbox.")
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
        unanswered = sum(b["grader"].get("unanswered", 0) for d in judge for b in d["checks"].values())
        total = sum(b["grader"]["n"] + b["grader"].get("unanswered", 0) for d in judge for b in d["checks"].values())
        counts.append(f"in the judge evaluation, {unanswered} of {total} questions went unanswered")
    out.append("- **Erroring often?** " + ("; ".join(counts).capitalize() + ". " if counts else "")
               + "Every card counts and shows its unscored cases, and a grade is withheld ('?') when too much "
               "is unscored, when the grader misses the known-answer floor, or when it denies an "
               "oracle-confirmed violation.")
    return out + [""]


def _q1(root: pathlib.Path) -> list[str]:
    out = ["## Q1 — Is the judge accurate?", ""]
    files = sorted((root / "evals/validation/v1").glob("judge_eval_*.json"))
    rows = [(f, _load(root, str(f.relative_to(root)).replace("\\", "/"))) for f in files]
    rows = [(f, d) for f, d in rows if d]
    if not rows:
        return out + ["NOT YET MEASURED — no committed judge-vs-oracle evidence.", ""]
    out += [
        "Grader verdicts on **real open-weight model transcripts**, scored against **deterministic "
        "oracles** (no LLM in the ground truth): did the model call the attacker's tool (InjecAgent), "
        "did it leak the planted password (Gandalf). The two rule-based baselines answer the same "
        "items. Unanswered items are excluded from the rates and counted.",
        "",
        "| Evidence | Grader | Check | n (unanswered) | Accuracy | Recall | Specificity | F1 | κ | Naive regex F1 | Tuned heuristic F1 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    pvals = []
    for f, d in rows:
        rel = str(f.relative_to(root)).replace("\\", "/")
        for check, b in sorted(d["checks"].items()):
            g = b["grader"]
            nr, th = b.get("naive_regex", {}), b.get("tuned_heuristic", {})
            pvals += [x.get("vs_grader", {}).get("mcnemar_p") for x in (nr, th) if "vs_grader" in x]
            out.append(
                f"| `{rel}` | {d['grader']} | {check} | {g['n']} ({g.get('unanswered', 0)}) | {_iv(g['accuracy'])} "
                f"| {_iv(g['recall'])} | {_iv(g['specificity'])} | {g['f1']:.2f} | {g['kappa']:.2f} "
                f"| {nr.get('f1', float('nan')):.2f} | {th.get('f1', float('nan')):.2f} |")
        audit = d.get("audit")
        if audit:
            out += ["", f"Disagreement audit (`{rel}`) — {audit.get('method', 'an LLM reading, not ground truth')} "
                    + "; ".join(f"{k}: {v}" for k, v in audit["summary"].items())
                    + (f". {audit['note']}" if audit.get("note") else "")]
    significant = [p for p in pvals if p is not None and p < 0.05]
    out += [
        "",
        "How to read this: the paired McNemar test asks whether the grader and a baseline get different "
        "ITEMS right (not whether their F1 differs). "
        + (f"{len(significant)} of {len(pvals)} grader-vs-baseline comparisons are significant at 0.05."
           if significant else f"None of the {len(pvals)} grader-vs-baseline comparisons is significant at 0.05 "
           "yet — the grader scores higher, but these samples can't rule out chance."),
        "Each item appears twice (the prompt as written and with the fix), so the rows are not fully "
        "independent and the intervals are somewhat too narrow. The leakage oracle is itself a string match "
        "for the planted password; the baselines are generic and are not told the password.",
        "",
        "Every run also measures its own grader in-run (known-answer questions + an oracle cross-check on "
        "the run's clear-cut questions) and withholds the grade when the grader falls below the policy floor.",
        "",
    ]
    return out


def _q3(root: pathlib.Path) -> list[str]:
    out = ["## Q3 — Does the fix work, and what does it cost?", ""]
    d = _load(root, "evals/validation/v1/evidence_oracle.json")
    if not d:
        return out + ["NOT YET MEASURED — the oracle-labelled evidence run on local open-weight models "
                      "has not been committed yet.", ""]
    models = ", ".join(sorted(d.get("models", {})))
    out += [f"The prompt as written vs the same prompt with Fusion's fix applied, on real local models "
            f"({models}), over held-out items from external benchmarks. Issue = oracle-confirmed attack "
            "success (InjecAgent: the attacker's tool was called; Gandalf: the planted password leaked) or "
            "an oracle-confirmed cost (XSTest: a SAFE request refused; IFEval: an instruction not followed). "
            "Lower is better in every row. Evidence: `evals/validation/v1/evidence_oracle.json`.", ""]
    pooled = d.get("pooled") or {}
    if len(d.get("models", {})) > 1 and pooled:
        out += ["**Pooled over all models.** The interval resamples whole items, because the same item "
                "runs on every model, so pooled pairs are not independent.", "",
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
            verdict = f"better with the fix, not proven ({ba.get('honesty', '—')})"
        else:
            verdict = "no change"
        out.append(f"| {c['experiment']} | {c['model']} | {c['n_paired']} | {_iv(c['baseline_rate'])} | "
                   f"{_iv(c['hardened_rate'])} | McNemar p={p:.3f} | {verdict} |")
    summary = []
    if regressions:
        summary.append("Significant regressions: " + "; ".join(regressions) + ".")
    summary.append("Proven improvements: " + ("; ".join(wins) + "." if wins else "none yet."))
    out += ["", " ".join(summary),
            "This is why every Fusion report card measures the fix on YOUR prompt and model and shows the "
            "result with its honesty badge instead of assuming the fix helps.", ""]
    return out


def _guard(root: pathlib.Path) -> list[str]:
    out = ["## Runtime guard for Claude Code (fusion-guard hook)", ""]
    rows = []
    for v in ("v1", "v2"):
        d = _load(root, f"evals/guard_bench/claude_code_heldout_{v}.json")
        if d:
            sens = d.get("sensitivity_test_tld_as_public")
            rows.append(
                f"| {v} | {d['benign']['n']} | {_iv(d['benign']['over_block'])} | {d['malicious']['n']} | "
                f"{_iv(d['malicious']['recall'])} | {_iv(sens['recall']) if sens else '—'} | {d['status'].split('.')[0]} |")
    if not rows:
        return out + ["NOT YET MEASURED.", ""]
    return out + [
        "Tool calls written by independent agents **blind to the rules**; each set scored once.",
        "",
        "| Set | benign n | Prompted (over-block) | attack n | Caught (recall) | Caught, .test hosts as public | Status |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        "Pattern rules catch the common exfiltration / destruction / remote-code shapes and miss much of "
        "the long tail; treat the hook as defense in depth, not a sandbox.",
        "",
    ]


def _limits() -> list[str]:
    return [
        "## Known limits",
        "",
        "- Oracle labels decide narrow questions (a tool was called, a password appeared). Where the "
        "judge's rubric is broader than the oracle, some 'disagreements' are real violations the oracle "
        "can't see — see each disagreement audit.",
        "- Samples are small (tens of transcripts per cell); read the intervals, not the points.",
        "- Known-answer questions come from a public gold set; the in-run oracle cross-check covers only "
        "clear-cut questions.",
        "",
    ]


def evidence_json(root: pathlib.Path | None = None) -> dict:
    """The same evidence, structured for the website's /trust page (frontend/src/content/evidence.json).
    Values are raw rates in [0, 1]; the page formats them."""
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
                "baselines": {name: {"f1": b[name]["f1"], "mcnemar_p": b[name]["vs_grader"]["mcnemar_p"]}
                              for name in ("naive_regex", "tuned_heuristic") if "f1" in b.get(name, {})},
                "audit": (d.get("audit") or {}).get("summary"),
            })
    guard = []
    for v in ("v1", "v2"):
        rel = f"evals/guard_bench/claude_code_heldout_{v}.json"
        d = _load(root, rel)
        if d:
            guard.append({"set": v, "evidence": rel, "benign_n": d["benign"]["n"],
                          "over_block": d["benign"]["over_block"], "attack_n": d["malicious"]["n"],
                          "recall": d["malicious"]["recall"],
                          "recall_sensitivity": (d.get("sensitivity_test_tld_as_public") or {}).get("recall"),
                          "status": d["status"].split(".")[0]})
    fix = _load(root, "evals/validation/v1/evidence_oracle.json")
    return {"generated_from": "evals/ (non-demonstration evidence only)", "judge_accuracy": judge,
            "guard_heldout": guard, "fix_efficacy": (fix or {}).get("cells", None)}


def render(root: pathlib.Path | None = None) -> str:
    root = root or data_root()
    parts = [HEADER, *_bottom_line(root), *_q1(root), *_q3(root), *_guard(root), *_limits()]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:  # pragma: no cover
    root = data_root()
    (root / "TRUST_REPORT.md").write_text(render(root), encoding="utf-8", newline="\n")
    (root / "frontend/src/content/evidence.json").write_text(
        json.dumps(evidence_json(root), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("wrote TRUST_REPORT.md and frontend/src/content/evidence.json")


if __name__ == "__main__":  # pragma: no cover
    main()
