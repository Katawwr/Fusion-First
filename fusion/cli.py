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
`scan` and `ci`) runs the real prompt through a model — needs ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

from fusion.attacks.taxonomy import Crosswalk
from fusion.engine.before_after import run_before_after
from fusion.engine.report import build_report_card, render_report_card_text
from fusion.goldset import gold_version_hash
from fusion.model.replay import Cassette, ReplayModelClient
from fusion.recording import CASSETTE_DIR, write_full_cassette
from fusion.stats.calibration import run_calibration
from fusion.stats.gate import run_eval_gate, save_baseline

_GRADE_ORDER = "ABCDF"


def _load_cassette(check: str, version: str) -> Cassette:
    path = CASSETTE_DIR / f"{check}.{version}.json"
    if not path.exists():
        print(f"no cassette at {path}; run: fusion record --check {check}")
        sys.exit(2)
    return Cassette.load(path)


def _resolve_checks(check: str) -> list[str]:
    if check == "all":
        from fusion.judge.rubric import REGISTRY

        return sorted(REGISTRY)
    return [check]


def cmd_record(args) -> int:
    for check in _resolve_checks(args.check):
        path = write_full_cassette(check, args.version)
        cas = Cassette.load(path)
        print(f"recorded {len(cas)} entries -> {path}")
    return 0


async def _eval_one(check: str, args) -> int:
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
    cas = _load_cassette(check, args.version)
    client = ReplayModelClient(cas, strict=True)
    outcome = await run_calibration(check, client, version=args.version, split=args.split)
    ba = await run_before_after(check, client, version=args.version)
    card = build_report_card(
        target_name=args.target,
        check=check,
        judge_accuracy=outcome.result,
        before_after=ba,
        judge_model="demo-heuristic-judge",
        gold_version=outcome.gold_version,
        crosswalk_version=Crosswalk().code_version(),
        demonstration=True,
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
    --min-grade on any check. Drop into a pipeline to stop an unsafe agent prompt from shipping."""
    import json as _json

    from fusion.engine.report import grade_for_rate
    from fusion.integrations.agent_tools import scan_prompt
    from fusion.integrations.live import LiveUnavailable

    src = pathlib.Path(args.prompt)
    if not src.exists():
        print(f"prompt file not found: {src}")
        return 2
    min_grade = args.min_grade.upper()
    if min_grade not in _GRADE_ORDER:
        print(f"--min-grade must be one of {list(_GRADE_ORDER)}")
        return 2

    checks = None if args.check == "all" else [args.check]
    try:
        result = asyncio.run(scan_prompt(src.read_text(encoding="utf-8"), checks, live=args.live))
    except LiveUnavailable as e:
        print(str(e))
        return 2

    rows, failures = [], []
    for c in result["checks"]:
        base_grade = grade_for_rate(c["baseline_issue_rate"] or 0.0)
        ok = _GRADE_ORDER.index(base_grade) <= _GRADE_ORDER.index(min_grade)
        rows.append({**c, "baseline_grade": base_grade, "pass": ok})
        if not ok:
            failures.append((c["check"], base_grade))

    if args.json:
        print(_json.dumps({"min_grade": min_grade, "passed": not failures, "checks": rows}, indent=2))
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
    ps.add_argument("--live", action="store_true", help="run against real models (needs API keys)")
    ps.add_argument("--target", default="Your prompt", help="display name for the scan target")
    ps.add_argument("--target-model", default="claude-haiku-4-5", help="target model id for --live")
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
    pci.add_argument("--live", action="store_true", help="grade the real prompt via a model (needs API keys)")
    pci.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    ph = sub.add_parser("harden", help="auto-apply the safety guardrails to a system-prompt file")
    ph.add_argument("--prompt", required=True, help="path to the system-prompt text file")
    ph.add_argument("--check", default="all")
    ph.add_argument("--out", default=None, help="write hardened prompt here (default: stdout)")
    ph.add_argument("--write", action="store_true", help="edit the prompt file in place")
    return p


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; force UTF-8 so output never mojibakes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    dispatch = {
        "record": cmd_record,
        "fix": cmd_fix,
        "harden": cmd_harden,
        "guard-proof": cmd_guard_proof,
        "guard-bench": cmd_guard_bench,
        "ci": cmd_ci,
    }
    async_dispatch = {"eval": _eval, "prove": _prove, "scan": _scan}
    if args.cmd in dispatch:
        return dispatch[args.cmd](args)
    if args.cmd in async_dispatch:
        return asyncio.run(async_dispatch[args.cmd](args))
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
