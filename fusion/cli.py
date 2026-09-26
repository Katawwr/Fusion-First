"""Fusion First CLI — the installed `fusion` command (also runnable as `python -m fusion.cli`).

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
`scan` and `ci`) runs the real prompt through a model — a local Ollama model and/or the `claude` CLI
subscription. Metered API keys are never used unless you pass `--backend api` AND set
FUSION_ALLOW_API_SPEND=1 (an API key merely present in the environment is ignored).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from fusion._data import data_root

# Heavy modules (schemas, judge, engine, stats) are imported inside the commands that use them, so
# `fusion hook …` — which runs before EVERY Claude Code tool call — starts in milliseconds.
CASSETTE_DIR = data_root() / "cassettes"  # == fusion.recording.CASSETTE_DIR
_GRADE_ORDER = "ABCDF"


class CliUsageError(Exception):
    """A user-facing problem (missing input, nothing recorded yet): printed, exit code 2."""


def _load_cassette(check: str, version: str):
    from fusion.judge.rubric import get_rubric
    from fusion.model.replay import Cassette

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
        # "all" means all SAFETY checks for the attack-suite commands (record/prove/scan/fix/harden);
        # quality checks (e.g. instruction_following) have no attack probes and are run explicitly.
        from fusion.judge.rubric import checks_of_kind

        return checks_of_kind("safety")
    if check == "all-quality":
        from fusion.judge.rubric import checks_of_kind

        return checks_of_kind("quality")
    return [check]


def cmd_record(args) -> int:
    if getattr(args, "live", False):
        return _record_live(args)
    from fusion.model.replay import Cassette
    from fusion.recording import write_full_cassette

    for check in _resolve_checks(args.check):
        path = write_full_cassette(check, args.version)
        cas = Cassette.load(path)
        print(f"recorded {len(cas)} entries -> {path}")
    return 0


def _record_live(args) -> int:
    """Record REAL judge verdicts (via the subscription CLI or an API key) into the committed
    cassette path, so `fusion eval`/`prove` run on real numbers instead of the heuristic stand-in."""
    import asyncio

    from fusion.integrations.live import LiveUnavailable, build_live_clients
    from fusion.recording import record_gold_cassette_live

    try:
        _target, judge, judge_id, choice = build_live_clients(max_calls=args.max_calls)
    except LiveUnavailable as e:
        print(str(e))
        return 2
    from fusion.judge.rubric import get_rubric

    splits = tuple(s.strip() for s in args.splits.split(",") if s.strip())
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else CASSETTE_DIR
    print(f"recording REAL judge verdicts (judge={judge_id}, independence={choice.independence})…")
    code = 0
    for check in _resolve_checks(args.check):
        # Quality checks have no attack probes — record the gold set only.
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
            print(f"    STOPPED: {report.aborted} — progress saved; re-run later to resume.")
            return 1
    return code


async def _measure(args) -> int:
    """The self-improving-loop command: run REAL sufficiency (are the attacks strong enough?) and,
    optionally, accuracy (Bar A) against live models, emitting one honest JSON summary."""
    import json as _json

    from fusion.integrations.live import LiveUnavailable, build_live_clients
    from fusion.measure.harness import load_reference_agents, measure_sufficiency
    from fusion.recording import record_gold_cassette_live
    from fusion.schemas import ScanTier

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
        print(f"Sufficiency — attacks vs live {args.target_model} (judge={judge_id}, {choice.independence}):")
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
        from fusion.judge.rubric import checks_of_kind, get_rubric
        from fusion.measure.harness import measure_quality

        system_prompt = "You are a helpful assistant."
        if getattr(args, "prompt", None) and pathlib.Path(args.prompt).exists():
            system_prompt = pathlib.Path(args.prompt).read_text(encoding="utf-8")
        quality_checks = (
            checks_of_kind("quality") if args.check == "all"
            else [c for c in checks if get_rubric(c).kind == "quality"]
        )
        if quality_checks:
            print(f"\nQuality — grade the agent on normal test inputs (target={args.target_model}):")
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
        from fusion.model.replay import ReplayModelClient
        from fusion.stats.calibration import run_calibration

        print(f"\nAccuracy (Bar A) — real judge vs oracle on the {args.split} split:")
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
    from fusion.goldset import gold_version_hash
    from fusion.model.replay import ReplayModelClient
    from fusion.stats.gate import run_eval_gate, save_baseline

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
    from fusion.attacks.taxonomy import Crosswalk
    from fusion.engine.before_after import run_before_after
    from fusion.engine.report import build_report_card, render_report_card_text
    from fusion.model.replay import ReplayModelClient, cassette_provenance
    from fusion.stats.calibration import run_calibration

    cas = _load_cassette(check, args.version)
    prov = cassette_provenance(cas)
    if prov.mixed:
        raise CliUsageError(
            f"{check}: cassette mixes answers from several models {sorted(prov.models)} — "
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
        from fusion.engine.report_html import render_dashboard_html

        title = "All checks" if args.check == "all" else args.check
        pathlib.Path(args.html).write_text(render_dashboard_html(cards, title), encoding="utf-8")
        print(f"wrote HTML report -> {args.html}")
    return 0


async def _scan(args) -> int:
    """Scan a user-supplied system prompt (the web-app flow, from the terminal)."""
    from fusion.engine.report import render_report_card_text
    from fusion.engine.user_scan import run_user_scan
    from fusion.integrations.live import LiveUnavailable, build_live_scan_kwargs
    from fusion.schemas import ScanEventType, ScanTier

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
    async for ev in run_user_scan(
        system_prompt=system_prompt, checks=checks, tier=tier, target_name=args.target, **scan_kwargs
    ):
        if ev.type == ScanEventType.CHECK_COMPLETED and ev.card is not None:
            cards.append(ev.card)
        elif ev.type == ScanEventType.SCAN_COMPLETED and ev.result is not None:
            print(f"\n=== Overall grade: {ev.result.overall_grade} "
                  f"({'DEMO' if ev.result.demonstration else 'REAL'}) ===\n")
    for card in cards:
        print(render_report_card_text(card))
        print("")
    if args.html:
        from fusion.engine.report_html import render_dashboard_html

        title = "All checks" if args.check == "all" else args.check
        pathlib.Path(args.html).write_text(render_dashboard_html(cards, title), encoding="utf-8")
        print(f"wrote HTML report -> {args.html}")
    return 0


def cmd_guard_proof(args) -> int:
    from fusion.guardrail.simulate import run_guard_before_after

    print("Runtime guardrail effectiveness (recorded attack -> guard-protected, prompt unchanged):")
    for check in _resolve_checks(args.check):
        r = run_guard_before_after(check)
        print(
            f"  {check:24} {r.baseline_issue_rate:.0%} -> {r.hardened_issue_rate:.0%}  "
            f"reduction {r.absolute_reduction.pct()}  McNemar p={r.mcnemar_p:.3f}  [{r.honesty.value}]"
        )
    return 0


def cmd_ci(args) -> int:
    """CI gate: scan a system-prompt file and FAIL (exit 1) if the prompt as written scores below
    --min-grade on any check. Drop into a pipeline to stop an unsafe agent prompt from shipping.

    Gating needs `--live`: demonstration responses are canned and do not depend on the prompt, so a
    demo "gate" would fail every prompt (even a hardened one). Without --live the command refuses
    (exit 2); `--demo` runs an advisory, clearly-labelled demonstration that always exits 0."""
    import json as _json

    from fusion.integrations.agent_tools import scan_prompt
    from fusion.integrations.live import LiveUnavailable

    if not args.live and not args.demo:
        print(
            "fusion ci needs --live to gate: demonstration responses are canned and do not depend on "
            "your prompt. Use --live (local Ollama and/or the claude CLI subscription — no API key), "
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
        print(f"Fusion CI gate — prompt must score >= {min_grade} on every check ({mode}):")
        for r in rows:
            mark = "PASS" if r["pass"] else "FAIL"
            print(f"  [{mark}] {r['check']:24s} baseline grade {r['baseline_grade']}  "
                  f"(attacks landed {len(r['attacks_that_landed'])})")
        if failures:
            print(f"\nFAILED: {len(failures)} check(s) below {min_grade}. "
                  f"Run `fusion harden --prompt {src} --write` and re-scan.")
        else:
            print(f"\nPASSED: every check is at least {min_grade}.")
    if args.demo:
        return 0  # advisory only — canned data can never pass or fail a real prompt
    return 1 if failures else 0


def cmd_guard_bench(args) -> int:
    """Score the runtime guard against the independent, hand-labelled adversarial corpus."""
    from fusion.guardrail.benchmark import (
        format_report,
        load_baseline,
        run_benchmark,
        save_baseline,
    )

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
            print(f"\nREGRESSION vs baseline — new bypasses: {sorted(new_bypasses)} "
                  f"new over-blocks: {sorted(new_overblocks)}")
            return 1
    return 0


def cmd_fix(args) -> int:
    from fusion.engine.fixes import guard_block

    print(guard_block(_resolve_checks(args.check)))
    return 0


def cmd_harden(args) -> int:
    """Auto-apply the safety guardrails to a user's system-prompt file."""
    from fusion.engine.fixes import apply_fix

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

    ps = sub.add_parser("scan", help="scan a user system-prompt file (paste-a-prompt web flow)")
    ps.add_argument("--prompt", required=True, help="path to the system-prompt text file")
    ps.add_argument("--check", default="all")
    ps.add_argument("--tier", default="quick", choices=["quick", "full"])
    ps.add_argument("--live", action="store_true", help="run against real models (CLI subscription, API key, or Ollama)")
    ps.add_argument("--target", default="Your prompt", help="display name for the scan target")
    ps.add_argument("--target-model", default="claude-haiku-4-5", help="target model id (e.g. llama3.2 with --backend ollama)")
    ps.add_argument("--backend", default=None, choices=["auto", "cli", "api", "ollama"], help="target backend for --live")
    ps.add_argument("--html", default=None, help="write a branded HTML report to this path")

    pf = sub.add_parser("fix", help="print the safety guardrail block for a check (or all)")
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

    from fusion.runs.cli import add_parsers as _add_run_parsers

    _add_run_parsers(sub)

    ppf = sub.add_parser("import-promptfoo", help="honest stats (Wilson CI, paired McNemar) on a promptfoo results.json")
    ppf.add_argument("results", help="promptfoo eval output (promptfoo eval -o results.json)")
    ppf.add_argument("--json", action="store_true")

    pk = sub.add_parser("hook", help="Claude Code hook entry point (fusion-guard plugin): reads the event on stdin")
    pk.add_argument("event", choices=["pre-tool-use", "post-tool-use"])

    ph = sub.add_parser("harden", help="auto-apply the safety guardrails to a system-prompt file")
    ph.add_argument("--prompt", required=True, help="path to the system-prompt text file")
    ph.add_argument("--check", default="all")
    ph.add_argument("--out", default=None, help="write hardened prompt here (default: stdout)")
    ph.add_argument("--write", action="store_true", help="edit the prompt file in place")
    return p


def _cmd_run(args) -> int:
    from fusion.runs.cli import cmd_run

    return cmd_run(args)


def _cmd_import_promptfoo(args) -> int:
    import json as _json

    from fusion.integrations.promptfoo import analyze_results, format_analysis, load_results

    try:
        a = analyze_results(load_results(args.results))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(_json.dumps(a, indent=2) if args.json else format_analysis(a))
    return 0


def _cmd_hook(args) -> int:
    import json as _json

    from fusion.integrations.claude_hooks import read_stdin, run_hook

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
    from fusion.runs.cli import cmd_doctor

    return cmd_doctor(args)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; force UTF-8 so output never mojibakes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "hook" and argv[1] in _HOOK_EVENTS:
        # Hot path (before every tool call): skip building the full parser, which imports the run
        # engine, and go straight to the guard.
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
