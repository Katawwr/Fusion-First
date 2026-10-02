"""Fusion First CLI: the installed `fusion` command (also runnable as `python -m fusion_first.cli`).

    fusion record  --check direct_prompt_injection
    fusion eval    --check all [--update-baseline]
    fusion prove   --check all [--html report.html]
    fusion scan    --prompt my_prompt.txt [--live]
    fusion harden  --prompt my_prompt.txt --write
    fusion fix     --check all
    fusion guard-proof --check all
    fusion guard-bench [--update-baseline]
    fusion ci      --prompt my_prompt.txt --min-grade B [--live]

Everything runs offline against committed cassettes (deterministic, no API keys). `--live` (on
`scan` and `ci`) runs the real prompt through a model: a local Ollama model and/or the `claude` CLI
subscription. Metered API keys are never used unless you pass `--backend api` AND set
FUSION_ALLOW_API_SPEND=1 (an API key merely present in the environment is ignored).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from fusion_first._data import data_root

# Heavy modules are imported inside the commands that use them, so `fusion hook` (run before EVERY
# Claude Code tool call) starts in milliseconds.
CASSETTE_DIR = data_root() / "cassettes"  # == fusion_first.recording.CASSETTE_DIR
_GRADE_ORDER = "ABCDF"


class CliUsageError(Exception):
    """A user-facing problem (missing input, nothing recorded yet): printed, exit code 2."""


def _load_cassette(check: str, version: str):
    from fusion_first.judge.rubric import get_rubric
    from fusion_first.model.replay import Cassette

    path = CASSETTE_DIR / f"{check}.{version}.json"
    if not path.exists():
        live = " --live" if get_rubric(check).kind == "quality" else ""
        hint = " (quality checks have no offline stand-in judge)" if live else ""
        raise CliUsageError(
            f"no cassette at {path}{hint}; run: fusion record --check {check}{live}"
        )
    return Cassette.load(path)


def _resolve_checks(check: str) -> list[str]:
    if check == "all":
        # "all" means the SAFETY checks: quality checks have no attack probes and are run explicitly.
        from fusion_first.judge.rubric import checks_of_kind

        return checks_of_kind("safety")
    if check == "all-quality":
        from fusion_first.judge.rubric import checks_of_kind

        return checks_of_kind("quality")
    return [check]


def _refuses_installed_copy(command: str) -> bool:
    """Dev commands that rewrite the corpora refuse on a pip install (they live inside site-packages)."""
    from fusion_first import _data

    if not _data.is_installed_copy():
        return False
    print(f"`fusion {command}` rewrites Fusion's committed data, which a pip install keeps inside the package. "
          "Run it from a source checkout, or set FUSION_DATA_DIR to a copy you own.", file=sys.stderr)
    return True


def cmd_record(args) -> int:
    if not (getattr(args, "live", False) and args.out_dir) and _refuses_installed_copy("record"):
        return 2
    if getattr(args, "live", False):
        return _record_live(args)
    from fusion_first.model.replay import Cassette
    from fusion_first.recording import write_full_cassette

    for check in _resolve_checks(args.check):
        path = write_full_cassette(check, args.version)
        cas = Cassette.load(path)
        print(f"recorded {len(cas)} entries -> {path}")
    return 0


def _record_live(args) -> int:
    """Record real judge verdicts into the cassette path, so `eval`/`prove` use real numbers."""
    import asyncio

    from fusion_first.integrations.live import LiveUnavailable, build_live_clients
    from fusion_first.recording import record_gold_cassette_live

    try:
        _target, judge, judge_id, choice = build_live_clients(max_calls=args.max_calls)
    except LiveUnavailable as e:
        print(str(e))
        return 2
    from fusion_first.judge.rubric import get_rubric

    splits = tuple(s.strip() for s in args.splits.split(",") if s.strip())
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else CASSETTE_DIR
    print(f"recording REAL judge verdicts (judge={judge_id}, independence={choice.independence})…")
    code = 0
    for check in _resolve_checks(args.check):
        include_probes = get_rubric(check).kind == "safety"
        path = out_dir / f"{check}.{args.version}.json"
        report = asyncio.run(
            record_gold_cassette_live(
                check, judge, version=args.version, splits=splits,
                include_probes=include_probes, concurrency=args.concurrency,
                path=path, resume=not args.fresh,
            )
        )
        cas = report.cassette
        models = sorted(cas.models())
        print(f"  {check}: {len(cas)} entries (+{report.recorded} new, models={models}) -> {path}")
        if report.failed:
            code = 1
            print(f"    {len(report.failed)} case(s) failed (re-run to retry): {report.failed[:5]}")
        if report.aborted:
            print(f"    STOPPED: {report.aborted}: progress saved; re-run later to resume.")
            return 1
    return code


async def _measure(args) -> int:
    """Measure attack sufficiency and, optionally, judge accuracy (Bar A) against live models."""
    import json as _json

    from fusion_first.integrations.live import LiveUnavailable, build_live_clients
    from fusion_first.measure.harness import load_reference_agents, measure_sufficiency
    from fusion_first.recording import record_gold_cassette_live
    from fusion_first.schemas import ScanTier

    try:
        target, judge, judge_id, choice = build_live_clients(
            target_model=args.target_model, max_calls=args.max_calls
        )
    except LiveUnavailable as e:
        print(str(e))
        return 2

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    checks = _resolve_checks(args.check)
    tier = ScanTier.FULL if args.tier == "full" else ScanTier.QUICK
    summary: dict = {"judge": judge_id, "independence": choice.independence, "target": args.target_model, "checks": {}}

    if "sufficiency" in stages:
        prompts = load_reference_agents()
        print(f"Sufficiency: attacks vs live {args.target_model} (judge={judge_id}, {choice.independence}):")
        for check in checks:
            res = await measure_sufficiency(
                check, target, judge, target_model_id=args.target_model,
                prompts=prompts, tier=tier, floor=args.floor, concurrency=args.concurrency,
            )
            print("  " + res.summary())
            summary["checks"].setdefault(check, {})["sufficiency"] = {
                "baseline_issue_rate": res.baseline_issue_rate,
                "n_landed": res.n_landed, "n": res.n, "n_errored": res.n_errored,
                "sufficient": res.sufficient,
            }

    if "quality" in stages:
        from fusion_first.judge.rubric import checks_of_kind, get_rubric
        from fusion_first.measure.harness import measure_quality

        system_prompt = "You are a helpful assistant."
        if getattr(args, "prompt", None) and pathlib.Path(args.prompt).exists():
            system_prompt = pathlib.Path(args.prompt).read_text(encoding="utf-8")
        quality_checks = (
            checks_of_kind("quality") if args.check == "all"
            else [c for c in checks if get_rubric(c).kind == "quality"]
        )
        if quality_checks:
            print(f"\nQuality: grade the agent on normal test inputs (target={args.target_model}):")
        for check in quality_checks:
            res = await measure_quality(
                check, target, judge, system_prompt,
                target_model_id=args.target_model, version=args.version, concurrency=args.concurrency,
            )
            print("  " + res.summary())
            summary["checks"].setdefault(check, {})["quality"] = {
                "grade": res.grade, "issue_rate": res.issue_rate,
                "n_defects": res.n_defects, "n": res.n, "n_errored": res.n_errored,
            }

    if "accuracy" in stages:
        from fusion_first.model.replay import ReplayModelClient
        from fusion_first.stats.calibration import run_calibration

        print(f"\nAccuracy (Bar A): real judge vs oracle on the {args.split} split:")
        for check in checks:
            report = await record_gold_cassette_live(
                check, judge, version=args.version, splits=(args.split,),
                include_probes=False, concurrency=args.concurrency,
            )
            if report.aborted:
                print(f"  {check}: STOPPED ({report.aborted})")
                break
            outcome = await run_calibration(
                check, ReplayModelClient(report.cassette, strict=True), version=args.version, split=args.split
            )
            r = outcome.result
            print(f"  {check:24} F1={r.f1:.2f} kappa={r.cohen_kappa:.2f} "
                  f"precision={r.precision.point:.2f} recall={r.recall.point:.2f} (n={r.n})")
            summary["checks"].setdefault(check, {})["accuracy"] = {
                "f1": r.f1, "kappa": r.cohen_kappa, "precision": r.precision.point,
                "recall": r.recall.point, "n": r.n, "n_unscored": r.n_unscored,
            }

    if args.json:
        pathlib.Path(args.json).write_text(_json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nwrote summary -> {args.json}")
    return 0


async def _eval_one(check: str, args) -> int:
    from fusion_first.goldset import gold_version_hash
    from fusion_first.model.replay import ReplayModelClient
    from fusion_first.stats.gate import run_eval_gate, save_baseline

    if args.update_baseline and _refuses_installed_copy("eval --update-baseline"):
        return 2
    cas = _load_cassette(check, args.version)
    client = ReplayModelClient(cas, strict=True)
    gate, result = await run_eval_gate(check, client, version=args.version, split=args.split)
    print(gate.summary())
    if args.update_baseline:
        p = save_baseline(check, result, gold_version_hash(check, args.version), args.split)
        print(f"baseline updated -> {p}")
        return 0
    return 0 if (gate.passed or gate.advisory) else 1


async def _eval(args) -> int:
    codes = [await _eval_one(c, args) for c in _resolve_checks(args.check)]
    return max(codes) if codes else 0


async def _prove_one(check: str, args):
    from fusion_first.attacks.taxonomy import Crosswalk
    from fusion_first.engine.before_after import run_before_after
    from fusion_first.engine.report import build_report_card, render_report_card_text
    from fusion_first.model.replay import ReplayModelClient, cassette_provenance
    from fusion_first.stats.calibration import run_calibration

    cas = _load_cassette(check, args.version)
    prov = cassette_provenance(cas)
    if prov.mixed:
        raise CliUsageError(
            f"{check}: cassette mixes answers from several models {sorted(prov.models)}: "
            "re-record it from one judge before proving anything"
        )
    client = ReplayModelClient(cas, strict=True, expected_models=prov.models)
    outcome = await run_calibration(check, client, version=args.version, split=args.split)
    ba = await run_before_after(check, client, version=args.version)
    card = build_report_card(
        target_name=args.target,
        check=check,
        judge_accuracy=outcome.result,
        before_after=ba,
        judge_model=next(iter(prov.models)) if prov.models else "unknown",
        gold_version=outcome.gold_version,
        crosswalk_version=Crosswalk().code_version(),
        demonstration=prov.demonstration,
    )
    print(render_report_card_text(card))
    print("")
    if args.json:
        out = args.json if args.check != "all" else f"{check}.{args.json}"
        pathlib.Path(out).write_text(card.model_dump_json(indent=2), encoding="utf-8")
        print(f"wrote {out}\n")
    return card


async def _prove(args) -> int:
    cards = [await _prove_one(check, args) for check in _resolve_checks(args.check)]
    if args.html:
        from fusion_first.engine.report_html import render_dashboard_html

        title = "All checks" if args.check == "all" else args.check
        pathlib.Path(args.html).write_text(render_dashboard_html(cards, title), encoding="utf-8")
        print(f"wrote HTML report -> {args.html}")
    return _release_gate(cards, args.policy) if args.gate else 0


def _release_gate(cards, policy_path: str | None) -> int:
    """Exit 1 unless every card clears the policy: judge floor + require_before_after_honesty."""
    from fusion_first.stats.gate import load_policy, release_gate

    failed = False
    for card in cards:
        if card.judge_accuracy is None or card.before_after is None:
            print(f"GATE FAIL {card.check}\n  missing evidence: the card has no judge accuracy or before/after")
            failed = True
            continue
        policy = load_policy(card.check, pathlib.Path(policy_path) if policy_path else None)
        result = release_gate(card.check, card.judge_accuracy, card.before_after, policy=policy)
        print(result.summary())
        failed = failed or not result.passed
    if any(c.demonstration for c in cards):
        print("DEMONSTRATION evidence (offline stand-in judge): the gate checks the pipeline, not a real agent.")
    return 1 if failed else 0


async def _scan(args) -> int:
    """Scan a user-supplied system prompt (the web-app flow, from the terminal)."""
    from fusion_first.engine.report import render_report_card_text
    from fusion_first.engine.user_scan import run_user_scan
    from fusion_first.integrations.live import LiveUnavailable, build_live_scan_kwargs
    from fusion_first.schemas import ScanEventType, ScanTier

    src = pathlib.Path(args.prompt)
    if not src.exists():
        print(f"prompt file not found: {src}")
        return 2
    system_prompt = src.read_text(encoding="utf-8")
    checks = _resolve_checks(args.check)
    tier = ScanTier.FULL if args.tier == "full" else ScanTier.QUICK

    if args.live:
        try:
            scan_kwargs = build_live_scan_kwargs(target_model=args.target_model)
        except LiveUnavailable as e:
            print(str(e))
            return 2
    else:
        scan_kwargs = {"demonstration": True}

    cards = []
    outcomes = []
    async for ev in run_user_scan(
        system_prompt=system_prompt, checks=checks, tier=tier, target_name=args.target, **scan_kwargs
    ):
        if ev.type == ScanEventType.CHECK_COMPLETED and ev.card is not None:
            cards.append(ev.card)
        elif ev.type == ScanEventType.SCAN_COMPLETED and ev.result is not None:
            outcomes = ev.result.outcomes
            print(f"\n=== Overall grade: {ev.result.overall_grade} "
                  f"({'DEMO' if ev.result.demonstration else 'REAL'}) ===\n")
    for card in cards:
        print(render_report_card_text(card))
        print("")
    from fusion_first.engine.guard_replay import in_sample_payload

    replay = in_sample_payload(outcomes, cards)
    if replay:
        print(f"{replay['sentence']} {replay['setup']}")
    if args.html:
        from fusion_first.engine.report_html import render_dashboard_html

        title = "All checks" if args.check == "all" else args.check
        pathlib.Path(args.html).write_text(render_dashboard_html(cards, title, outcomes=outcomes), encoding="utf-8")
        print(f"wrote HTML report -> {args.html}")
    return 0


def cmd_guard_proof(args) -> int:
    from fusion_first.guardrail.simulate import run_guard_before_after

    print("Runtime guardrail effectiveness (recorded attack -> guard-protected, prompt unchanged):")
    for check in _resolve_checks(args.check):
        r = run_guard_before_after(check)
        print(
            f"  {check:24} {r.baseline_issue_rate:.0%} -> {r.hardened_issue_rate:.0%}  "
            f"reduction {r.absolute_reduction.pct()}  McNemar p={r.mcnemar_p:.3f}  [{r.honesty.value}]"
        )
    return 0


def cmd_ci(args) -> int:
    """CI gate: exit 1 if the prompt as written scores below --min-grade on any check. Needs `--live`
    (canned demo responses don't depend on the prompt); `--demo` is advisory and always exits 0."""
    import json as _json

    from fusion_first.integrations.agent_tools import scan_prompt
    from fusion_first.integrations.live import LiveUnavailable

    if not args.live and not args.demo:
        print(
            "fusion ci needs --live to gate: demonstration responses are canned and do not depend on "
            "your prompt. Use --live (local Ollama and/or the claude CLI subscription: no API key), "
            "or --demo for an advisory, non-gating demonstration run."
        )
        return 2

    src = pathlib.Path(args.prompt)
    if not src.exists():
        print(f"prompt file not found: {src}")
        return 2
    min_grade = args.min_grade.upper()
    if min_grade not in _GRADE_ORDER:
        print(f"--min-grade must be one of {list(_GRADE_ORDER)}")
        return 2

    import asyncio

    checks = None if args.check == "all" else [args.check]
    try:
        result = asyncio.run(scan_prompt(
            src.read_text(encoding="utf-8"), checks, live=bool(args.live),
            target_model=args.target_model, backend=args.backend,
        ))
    except LiveUnavailable as e:
        print(str(e))
        return 2

    rows, failures = [], []
    for c in result["checks"]:
        base_grade = c["grade"]  # the card's baseline grade; '?' = nothing measured
        ok = base_grade in _GRADE_ORDER and _GRADE_ORDER.index(base_grade) <= _GRADE_ORDER.index(min_grade)
        rows.append({**c, "baseline_grade": base_grade, "pass": ok})
        if not ok:
            failures.append((c["check"], base_grade))

    if args.demo:
        print("DEMONSTRATION (advisory, not a gate): canned responses that do not depend on your prompt.")
    if args.json:
        print(_json.dumps(
            {"min_grade": min_grade, "passed": not failures, "demonstration": result["demonstration"],
             "checks": rows}, indent=2,
        ))
    else:
        mode = "LIVE" if not result["demonstration"] else "DEMO"
        print(f"Fusion CI gate: prompt must score >= {min_grade} on every check ({mode}):")
        for r in rows:
            mark = "PASS" if r["pass"] else "FAIL"
            print(f"  [{mark}] {r['check']:24s} baseline grade {r['baseline_grade']}  "
                  f"(attacks landed {len(r['attacks_that_landed'])})")
        if failures:
            print(f"\nFAILED: {len(failures)} check(s) below {min_grade}. Add the runtime guardrail "
                  f"(fusion_first.guardrail); optionally `fusion harden --prompt {src} --write` and re-scan.")
        else:
            print(f"\nPASSED: every check is at least {min_grade}.")
    if args.demo:
        return 0  # advisory only: canned data can never pass or fail a real prompt
    return 1 if failures else 0


def cmd_guard_bench(args) -> int:
    """Score the runtime guard against the independent, hand-labelled adversarial corpus."""
    from fusion_first.guardrail.benchmark import (
        format_report,
        load_baseline,
        run_benchmark,
        save_baseline,
    )

    if args.update_baseline and _refuses_installed_copy("guard-bench --update-baseline"):
        return 2
    report = run_benchmark()
    print(format_report(report))
    if args.update_baseline:
        p = save_baseline(report)
        print(f"\nbaseline updated -> {p}")
        return 0
    base = load_baseline()
    if base is not None:
        new_bypasses = set(report.summary()["bypasses"]) - set(base.get("bypasses", []))
        new_overblocks = set(report.summary()["overblocks"]) - set(base.get("overblocks", []))
        if new_bypasses or new_overblocks:
            print(f"\nREGRESSION vs baseline: new bypasses: {sorted(new_bypasses)} "
                  f"new over-blocks: {sorted(new_overblocks)}")
            return 1
    return 0


def cmd_fix(args) -> int:
    from fusion_first.engine.fixes import guard_block

    print(guard_block(_resolve_checks(args.check)))
    return 0


def cmd_harden(args) -> int:
    """Optional: append the prompt fix to a user's system-prompt file (re-test it on the target model)."""
    from fusion_first.engine.fixes import apply_fix

    src = pathlib.Path(args.prompt)
    if not src.exists():
        print(f"prompt file not found: {src}")
        return 2
    original = src.read_text(encoding="utf-8")
    hardened = apply_fix(original, _resolve_checks(args.check))
    if args.write:
        src.write_text(hardened, encoding="utf-8")
        print(f"hardened in place -> {src}")
    elif args.out:
        pathlib.Path(args.out).write_text(hardened, encoding="utf-8")
        print(f"wrote hardened prompt -> {args.out}")
    else:
        print(hardened)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fusion")
    sub = p.add_subparsers(dest="cmd", required=True)
    common = dict(check="direct_prompt_injection", version="v1")

    pr = sub.add_parser("record")
    pr.add_argument("--check", default=common["check"])
    pr.add_argument("--version", default=common["version"])
    pr.add_argument("--live", action="store_true", help="record REAL judge verdicts (CLI subscription or API key)")
    pr.add_argument("--splits", default="dev,blind", help="gold splits to record when --live (default dev,blind)")
    pr.add_argument("--concurrency", type=int, default=4)
    pr.add_argument("--max-calls", type=int, default=1000)
    pr.add_argument("--out-dir", default=None, help="where to write live cassettes (default cassettes/)")
    pr.add_argument("--fresh", action="store_true", help="ignore any existing live recording (no resume)")

    pm = sub.add_parser("measure", help="self-improving loop: real sufficiency + accuracy vs live models")
    pm.add_argument("--check", default="all")
    pm.add_argument("--stages", default="sufficiency", help="comma list: sufficiency,accuracy,quality (default sufficiency)")
    pm.add_argument("--prompt", default=None, help="agent system-prompt file to grade in the quality stage")
    pm.add_argument("--target-model", default="claude-haiku-4-5", help="target model (e.g. llama3.2 with --backend ollama)")
    pm.add_argument("--backend", default=None, choices=["auto", "cli", "api", "ollama"], help="target backend (sets FUSION_TARGET_BACKEND)")
    pm.add_argument("--tier", default="quick", choices=["quick", "full"])
    pm.add_argument("--split", default="blind", help="gold split for the accuracy stage")
    pm.add_argument("--version", default=common["version"])
    pm.add_argument("--floor", type=float, default=0.20, help="sufficiency floor (baseline issue rate)")
    pm.add_argument("--concurrency", type=int, default=4)
    pm.add_argument("--max-calls", type=int, default=1000)
    pm.add_argument("--json", default=None, help="write the JSON summary to this path")

    pe = sub.add_parser("eval")
    pe.add_argument("--check", default=common["check"])
    pe.add_argument("--version", default=common["version"])
    pe.add_argument("--split", default="blind")
    pe.add_argument("--update-baseline", action="store_true")

    pp = sub.add_parser("prove")
    pp.add_argument("--check", default=common["check"])
    pp.add_argument("--version", default=common["version"])
    pp.add_argument("--split", default="blind")
    pp.add_argument("--target", default="Demo target")
    pp.add_argument("--json", default=None)
    pp.add_argument("--html", default=None, help="write a branded HTML report dashboard to this path")
    pp.add_argument("--gate", action="store_true",
                    help="exit 1 unless every card clears the policy (judge floor + require_before_after_honesty)")
    pp.add_argument("--policy", default=None, help="policy file for --gate (default: evals/policy.yaml)")

    ps = sub.add_parser("scan", help="scan a user system-prompt file (paste-a-prompt web flow)")
    ps.add_argument("--prompt", required=True, help="path to the system-prompt text file")
    ps.add_argument("--check", default="all")
    ps.add_argument("--tier", default="quick", choices=["quick", "full"])
    ps.add_argument("--live", action="store_true", help="run against real models (CLI subscription, API key, or Ollama)")
    ps.add_argument("--target", default="Your prompt", help="display name for the scan target")
    ps.add_argument("--target-model", default="claude-haiku-4-5", help="target model id (e.g. llama3.2 with --backend ollama)")
    ps.add_argument("--backend", default=None, choices=["auto", "cli", "api", "ollama"], help="target backend for --live")
    ps.add_argument("--html", default=None, help="write a branded HTML report to this path")

    pf = sub.add_parser("fix", help="optional: print the prompt-fix block for a check (or all)")
    pf.add_argument("--check", default="all")

    pg = sub.add_parser("guard-proof", help="measure the runtime guardrail's issue-rate reduction")
    pg.add_argument("--check", default="all")

    pgb = sub.add_parser("guard-bench", help="score the guard on the independent adversarial corpus")
    pgb.add_argument("--update-baseline", action="store_true", help="snapshot current metrics as the regression baseline")

    pci = sub.add_parser("ci", help="CI gate: fail the build if a prompt scores below --min-grade")
    pci.add_argument("--prompt", required=True, help="path to the system-prompt text file")
    pci.add_argument("--check", default="all")
    pci.add_argument("--min-grade", default="B", help="minimum acceptable baseline grade A-F (default B)")
    pci.add_argument("--live", action="store_true", help="grade the real prompt via a model (Ollama and/or claude CLI subscription)")
    pci.add_argument("--demo", action="store_true", help="advisory demonstration run (canned data, never gates; exit 0)")
    pci.add_argument("--backend", default=None, choices=["auto", "cli", "ollama", "api"], help="live backend (default auto)")
    pci.add_argument("--target-model", default=None, help="target model (e.g. llama3.2:1b with --backend ollama)")
    pci.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    from fusion_first.runs.cli import add_parsers as _add_run_parsers

    _add_run_parsers(sub)

    ppf = sub.add_parser("import-promptfoo", help="honest stats (Wilson CI, paired McNemar) on a promptfoo results.json")
    ppf.add_argument("results", help="promptfoo eval output (promptfoo eval -o results.json)")
    ppf.add_argument("--json", action="store_true")

    pk = sub.add_parser("hook", help="Claude Code hook entry point (fusion-guard plugin): reads the event on stdin")
    pk.add_argument("event", choices=["pre-tool-use", "post-tool-use"])

    ph = sub.add_parser("harden", help="optional: append the prompt fix to a system-prompt file (re-test it on your model)")
    ph.add_argument("--prompt", required=True, help="path to the system-prompt text file")
    ph.add_argument("--check", default="all")
    ph.add_argument("--out", default=None, help="write hardened prompt here (default: stdout)")
    ph.add_argument("--write", action="store_true", help="edit the prompt file in place")

    psv = sub.add_parser("serve", help="run the Fusion web app on this machine (127.0.0.1 only)")
    psv.add_argument("--port", type=int, default=8765)
    psv.add_argument("--host", default="127.0.0.1", help="loopback only: 127.0.0.1 or localhost")
    psv.add_argument("--dist", default=None, help="built frontend dir (default: frontend/dist or the bundled copy)")
    psv.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    psv.add_argument("--demo-only", action="store_true", help="keep live backends (Ollama, claude CLI) off")

    sub.add_parser("plugin-dir", help='print the Claude Code plugin marketplace path: '
                                      'claude plugin marketplace add "$(fusion plugin-dir)"')
    return p


def _cmd_run(args) -> int:
    from fusion_first.runs.cli import cmd_run

    return cmd_run(args)


def _cmd_import_promptfoo(args) -> int:
    import json as _json

    from fusion_first.integrations.promptfoo import analyze_results, format_analysis, load_results

    try:
        a = analyze_results(load_results(args.results))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(_json.dumps(a, indent=2) if args.json else format_analysis(a))
    return 0


def _cmd_hook(args) -> int:
    import json as _json

    from fusion_first.integrations.claude_hooks import read_stdin, run_hook

    try:
        text = read_stdin()  # bytes decoded as UTF-8: the Windows console code page must not crash it
    except (OSError, ValueError) as e:
        print(_json.dumps({"systemMessage": f"Fusion guard hook error (ignored): could not read the event: {e}"}))
        return 0
    code, out = run_hook(args.event, text)
    if out:
        print(out)
    return code


_HOOK_EVENTS = ("pre-tool-use", "post-tool-use")


def _cmd_doctor(args) -> int:
    from fusion_first.runs.cli import cmd_doctor

    return cmd_doctor(args)


def _cmd_serve(args) -> int:
    try:
        from fusion_first.web.serve import ServeError, serve
    except ImportError as e:
        print(f"fusion serve needs the web extras: pip install \"fusion-safety[serve]\" ({e})")
        return 2
    try:
        serve(host=args.host, port=args.port, dist=args.dist, open_browser=not args.no_open,
              local_backends=not args.demo_only)
    except ServeError as e:
        print(f"error: {e}")
        return 2
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_plugin_dir(args) -> int:
    from fusion_first import _data

    root = _data.plugin_root()
    if root is None:
        print("No plugin marketplace in this install. Reinstall: pip install fusion-safety", file=sys.stderr)
        return 1
    # Windows PowerShell 5.1 decodes `$(fusion plugin-dir)` with the console's OEM code page, not UTF-8:
    # a non-ASCII path arrives mangled, its 8.3 short form does not.
    print((not str(root).isascii() and _short_path(root)) or root)
    return 0


def _short_path(path) -> str | None:
    """The ASCII 8.3 form of an existing Windows path, or None (not Windows, 8.3 names off, still non-ASCII)."""
    if sys.platform != "win32":
        return None
    import ctypes

    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
    return buf.value if 0 < n < len(buf) and buf.value.isascii() else None


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; force UTF-8 so output never mojibakes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "hook" and argv[1] in _HOOK_EVENTS:
        # Hot path (before every tool call): skip the full parser, which imports the run engine.
        return _cmd_hook(argparse.Namespace(cmd="hook", event=argv[1]))
    args = build_parser().parse_args(argv)
    dispatch = {
        "record": cmd_record,
        "fix": cmd_fix,
        "harden": cmd_harden,
        "guard-proof": cmd_guard_proof,
        "guard-bench": cmd_guard_bench,
        "ci": cmd_ci,
        "run": _cmd_run,
        "hook": _cmd_hook,
        "import-promptfoo": _cmd_import_promptfoo,
        "doctor": _cmd_doctor,
        "serve": _cmd_serve,
        "plugin-dir": _cmd_plugin_dir,
    }
    if getattr(args, "backend", None):
        import os

        os.environ["FUSION_TARGET_BACKEND"] = args.backend
    async_dispatch = {"eval": _eval, "prove": _prove, "scan": _scan, "measure": _measure}
    try:
        if args.cmd in dispatch:
            return dispatch[args.cmd](args)
        if args.cmd in async_dispatch:
            import asyncio

            return asyncio.run(async_dispatch[args.cmd](args))
    except CliUsageError as e:
        print(str(e))
        return 2
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
