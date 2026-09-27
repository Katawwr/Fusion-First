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
        b3 = _load(root, B3_EVIDENCE)
        plain = ""
        if b3:
            p = b3["pooled"]
            plain = (" It also beats a plain one-question judge using the same model (pre-registered)."
                     if b3["decision"]["claim_allowed"] else
                     f" A plain one-question judge using the same model was just as accurate on the same items "
                     f"(rubric {_pct(p['rubric']['accuracy']['point'])}, plain "
                     f"{_pct(p['b3']['accuracy']['point'])}), so Fusion does not claim its rubric improves accuracy.")
        out.append(f"- **Detecting accurately?** Graded against deterministic oracles: {span}. "
                   + ("It beats the rule-based checks" if beats else "It does not always beat the rule-based checks")
                   + (" significantly." if sig else ", but not significantly yet (small samples).") + plain)
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
    runtime = _load(root, GUARDRAIL_EVIDENCE)
    if runtime:
        out.append(_guardrail_sentence(runtime, fix))
    guard = _guard_headline(root)
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


def _guard_sets(root: pathlib.Path) -> list[tuple[str, dict]]:
    """Every scored held-out set, oldest first."""
    found = []
    for i in range(1, 10):
        d = _load(root, f"evals/guard_bench/claude_code_heldout_v{i}.json")
        if d:
            found.append((f"v{i}", d))
    return found


def _guard_status(v: str, d: dict, sets: list[tuple[str, dict]]) -> str:
    """A held-out set stays the honest number only until a newer one is scored against changed rules."""
    status = d["status"].split(".")[0]
    newest_held_out = next((sv for sv, sd in reversed(sets) if sd["status"].startswith("HELD OUT")), None)
    if status.startswith("HELD OUT") and v != newest_held_out:
        return "SUPERSEDED (rules changed after scoring)"
    return status


def _guard_headline(root: pathlib.Path) -> dict | None:
    sets = _guard_sets(root)
    return next((d for _, d in reversed(sets) if d["status"].startswith("HELD OUT")), sets[-1][1] if sets else None)


def _guard(root: pathlib.Path) -> list[str]:
    out = ["## Runtime guard for Claude Code (fusion-guard hook)", ""]
    rows = []
    sets = _guard_sets(root)
    for v, d in sets:
        sens = d.get("sensitivity_test_tld_as_public")
        rows.append(
            f"| {v} | {d['benign']['n']} | {_iv(d['benign']['over_block'])} | {d['malicious']['n']} | "
            f"{_iv(d['malicious']['recall'])} | {_iv(sens['recall']) if sens else '—'} | "
            f"{_guard_status(v, d, sets)} |")
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
    sets = _guard_sets(root)
    for v, d in sets:
        guard.append({"set": v, "evidence": f"evals/guard_bench/claude_code_heldout_{v}.json",
                      "benign_n": d["benign"]["n"], "over_block": d["benign"]["over_block"],
                      "attack_n": d["malicious"]["n"], "recall": d["malicious"]["recall"],
                      "recall_sensitivity": (d.get("sensitivity_test_tld_as_public") or {}).get("recall"),
                      "status": _guard_status(v, d, sets)})
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
    runtime = _load(root, GUARDRAIL_EVIDENCE)
    runtime_guardrail = None
    if runtime:
        keep = ("attacks", "stopped", "recall", "clean", "over_blocked", "over_block")
        runtime_guardrail = {
            "evidence": GUARDRAIL_EVIDENCE, "models": runtime.get("models", []),
            "all": {k: runtime["all"][k] for k in keep},
            "by_attack_type": {g: {**{k: s[k] for k in keep}, "name": _ATTACK_TYPE_NAMES.get(g, g)}
                               for g, s in sorted(runtime["by_attack_type"].items())},
        }
    ledger = _load(root, LEDGER_EVIDENCE)
    counts = ("found", "fix_removed", "fix_caused", "guard_stopped", "either", "neither")
    value_ledger = None if not ledger else {
        "evidence": LEDGER_EVIDENCE,
        "total": {k: ledger["total"][k] for k in counts},
        "by_model": {m: {k: s[k] for k in counts} for m, s in ledger["by_model"].items()},
        "fix_refusal_cost": ledger.get("fix_refusal_cost"),
        "note": ledger.get("note"),
    }
    return {"generated_from": "evals/ (non-demonstration evidence only)", "judge_accuracy": judge,
            "rubric_vs_plain": rubric_vs_plain, "fix_pooled": fix_pooled or None,
            "runtime_guardrail": runtime_guardrail, "value_ledger": value_ledger,
            "guard_heldout": guard, "fix_efficacy": (fix or {}).get("cells", None)}


B3_EVIDENCE = "evals/validation/v1/b3_rubric_vs_plain_judge.json"
GUARDRAIL_EVIDENCE = "evals/validation/v1/guard_on_transcripts.json"
_ATTACK_TYPE_NAMES = {"gandalf:leak": "password leaks (Gandalf)",
                      "injecagent:ds": "tool hijack, data stealing (InjecAgent)",
                      "injecagent:dh": "tool hijack, direct harm (InjecAgent)"}


_ATTACK_TYPE_SHORT = {"gandalf:leak": "password leaks", "injecagent:ds": "data-stealing tool hijacks",
                      "injecagent:dh": "direct-harm tool hijacks"}


def _guardrail_sentence(d: dict, fix: dict | None) -> str:
    a = d["all"]
    ranked = sorted(d["by_attack_type"].items(), key=lambda kv: -kv[1]["recall"]["point"])
    parts = [f"{_pct(s['recall']['point'])} of {_ATTACK_TYPE_SHORT.get(k, k)}" for k, s in ranked]
    listed = ", ".join(parts[:-1]) + f" and {parts[-1]}" if len(parts) > 1 else "".join(parts)
    sentence = (f"- **Runtime guardrail in your agent?** On real attacks that succeeded against "
                f"{len(d.get('models', []))} small open-weight models it stopped {a['stopped']} of {a['attacks']}, "
                f"{_iv(a['recall'])}: {listed}. It wrongly blocked {_iv(a['over_block'])} of clean transcripts.")
    pooled = (fix or {}).get("pooled") or {}
    same = [pooled[e] for e in ("injecagent", "gandalf") if e in pooled]
    if same and all(_pooled_verdict(_pooled_ci(p)) == "no clear change" for p in same):
        sentence += " On the same attacks the prompt fix gave no clear reduction."
    return sentence


LEDGER_EVIDENCE = "evals/validation/v1/value_ledger.json"


def _ledger(root: pathlib.Path) -> list[str]:
    d = _load(root, LEDGER_EVIDENCE)
    if not d:
        return []
    head = ("| Model | Real attacks found | Removed by the prompt fix | New attacks the fix caused | "
            "Stopped by the guardrail | Caught by either | Got through both |")
    out = ["## Value ledger: what each layer bought on real attacks", "",
           "A re-reading of the committed measurements above (no new data): of the attacks that succeeded "
           f"with the prompt as written, what the fix removed and what the guardrail stopped. Evidence: `{LEDGER_EVIDENCE}`.",
           "", head, "|---|---|---|---|---|---|---|"]
    for name, s in [*d["by_model"].items(), ("all models", d["total"])]:
        out.append(f"| {name} | {s['found']} | {s['fix_removed']} | {s['fix_caused']} | {s['guard_stopped']} | "
                   f"{s['either']} | {s['neither']} |")
    cost = d.get("fix_refusal_cost") or {}
    out.append("")
    if cost:
        out.append(f"The fix also made the models refuse {cost['safe_requests_newly_refused']} safe requests they "
                   f"had answered (and answer {cost['safe_requests_newly_answered']} they had refused), out of "
                   f"{cost['pairs']} XSTest pairs.")
    if d.get("note"):
        out.append(f"Caveat: {d['note']}")
    return out + [""]


def _guardrail(root: pathlib.Path) -> list[str]:
    d = _load(root, GUARDRAIL_EVIDENCE)
    if not d:
        return []
    out = ["## Runtime guardrail on real attacks (pre-registered)", "",
           "The runtime guardrail (`fusion/guardrail`) applied to the attacks that really succeeded against "
           "the small models in the Q3 run (prompt as written), re-scored by the same oracles. Registered in "
           f"`evals/validation/v1/PREREG_guard_on_real_transcripts.md`; evidence: `{GUARDRAIL_EVIDENCE}`.", "",
           "| Attack | Real attacks | Stopped | Clean transcripts | Wrongly blocked |", "|---|---|---|---|---|"]
    for k, s in sorted(d["by_attack_type"].items()):
        out.append(f"| {_ATTACK_TYPE_NAMES.get(k, k)} | {s['attacks']} | {_iv(s['recall'])} | {s['clean']} | "
                   f"{_iv(s['over_block'])} |")
    a = d["all"]
    out.append(f"| all | {a['attacks']} | {_iv(a['recall'])} | {a['clean']} | {_iv(a['over_block'])} |")
    out.append("")
    out += [f"- {f}" for f in d.get("findings", [])]
    if d.get("deviation_note"):
        out.append(f"- Deviation, disclosed: {d['deviation_note']}")
    return out + [""]
COMPACT_EVIDENCE = "evals/validation/v1/compact_fix.json"


def _compact_verdict(dec: dict) -> str:
    per = dec["per_model"].values()
    if dec["adopt"]:
        return ("**Decision (registered rule): ADOPTED.** On at least one model the compact block cut attack "
                "success significantly without a meaningful rise in refusals of safe requests, and no model got "
                "significantly worse, so it becomes the default fix for small models.")
    why = ("a model got significantly MORE attacks with it" if any(m["attack_higher"] for m in per)
           else "no model met both primary outcomes (fewer attacks AND no meaningful rise in refusals)")
    return f"**Decision (registered rule): NOT ADOPTED** — {why}. The full fix stays, measured per model."


def _compact(root: pathlib.Path) -> list[str]:
    d = _load(root, COMPACT_EVIDENCE)
    if not d or "prereg_decision" not in d:
        return []
    dec = d["prereg_decision"]
    xs = {c["model"]: c for c in d.get("cells", []) if c["experiment"] == "xstest"}
    out = ["### Pre-registered: a compact fix for small models", "",
           "A few short rules ending with an instruction to otherwise help normally, compared with the prompt as "
           "written on FRESH items (none used to design any fix). Registered before any data in "
           f"`evals/validation/v1/PREREG_compact_fix.md`; evidence: `{COMPACT_EVIDENCE}`. Attacks = InjecAgent "
           "and Gandalf pooled per model.", "",
           "| Model | Attacks as written | With the compact block | Paired test | Refusals of safe requests "
           "(upper 95% bound of the rise) | Both primary outcomes met |",
           "|---|---|---|---|---|---|"]
    for model, a in sorted(d["attack_success_by_model"].items()):
        pm = dec["per_model"].get(model, {})
        drop = (xs.get(model) or {}).get("quality_drop") or {}
        rise = f"{drop['high'] * 100:+.0f} pts" if "high" in drop else "—"
        ni = "within 10 pts" if pm.get("over_refusal_noninferior") else "NOT within 10 pts"
        out.append(f"| {model} | {_iv(a['baseline_rate'])} | {_iv(a['treatment_rate'])} | "
                   f"McNemar p={a['before_after']['mcnemar_p']:.3f} | {rise} ({ni}) | "
                   f"{'yes' if pm.get('both_primary') else 'no'} |")
    return out + ["", _compact_verdict(dec), ""]


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
    out = ["## Q4 — Does the rubric beat simply asking an LLM?", "",
           "The same items graded twice by the same Claude Sonnet: once with Fusion's rubric (the Q1 "
           "answers), once asked one plain yes/no question with no rubric. Pre-registered in "
           "`evals/validation/v1/PREREG_b3_single_question.md`; evidence: "
           f"`{B3_EVIDENCE}`.", "",
           "| Check | n (plain unanswered) | Rubric judge | Plain judge | Difference, rubric minus plain (95% CI) "
           "| Paired test |", "|---|---|---|---|---|---|"]
    for name, b in [*sorted(d["by_check"].items()), ("pooled", d["pooled"])]:
        diff = b["accuracy_difference"]
        out.append(f"| {name} | {b['n']} ({b['b3_unanswered']}) | {_iv(b['rubric']['accuracy'])} | "
                   f"{_iv(b['b3']['accuracy'])} | {_pp(diff['point'])} ({diff['low'] * 100:+.0f} to "
                   f"{diff['high'] * 100:+.0f}) | McNemar p={b['mcnemar_p']:.3f} |")
    return out + ["", _b3_verdict(d), ""]


def render(root: pathlib.Path | None = None) -> str:
    root = root or data_root()
    parts = [HEADER, *_bottom_line(root), *_q1(root), *_q3(root), *_compact(root), *_b3(root),
             *_guardrail(root), *_ledger(root), *_guard(root), *_limits()]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:  # pragma: no cover
    root = data_root()
    (root / "TRUST_REPORT.md").write_text(render(root), encoding="utf-8", newline="\n")
    (root / "frontend/src/content/evidence.json").write_text(
        json.dumps(evidence_json(root), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("wrote TRUST_REPORT.md and frontend/src/content/evidence.json")


if __name__ == "__main__":  # pragma: no cover
    main()
