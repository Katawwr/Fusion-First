"""Fusion offline CLI: record cassettes, run the eval gate, and produce a report card.

    python scripts/fusion_cli.py record  --check direct_prompt_injection
    python scripts/fusion_cli.py eval    --check direct_prompt_injection [--update-baseline]
    python scripts/fusion_cli.py prove   --check direct_prompt_injection [--json out.json]

Everything runs offline against committed cassettes (deterministic, no API keys). Swapping in a
live Claude client at `record --live` (Phase 1 follow-up) produces real numbers with no other
change to the harness.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

# Allow running as a plain script (python scripts/fusion_cli.py ...)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fusion.attacks.taxonomy import Crosswalk  # noqa: E402
from fusion.engine.before_after import run_before_after  # noqa: E402
from fusion.engine.report import build_report_card, render_report_card_text  # noqa: E402
from fusion.goldset import gold_version_hash  # noqa: E402
from fusion.model.replay import Cassette, ReplayModelClient  # noqa: E402
from fusion.recording import CASSETTE_DIR, write_full_cassette  # noqa: E402
from fusion.stats.calibration import run_calibration  # noqa: E402
from fusion.stats.gate import (  # noqa: E402
    run_eval_gate,
    save_baseline,
)


def _load_cassette(check: str, version: str) -> Cassette:
    path = CASSETTE_DIR / f"{check}.{version}.json"
    if not path.exists():
        print(f"no cassette at {path}; run: python scripts/fusion_cli.py record --check {check}")
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


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; force UTF-8 so hook output never mojibakes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
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

    pf = sub.add_parser("fix", help="print the safety guardrail block for a check (or all)")
    pf.add_argument("--check", default="all")

    ph = sub.add_parser("harden", help="auto-apply the safety guardrails to a system-prompt file")
    ph.add_argument("--prompt", required=True, help="path to the system-prompt text file")
    ph.add_argument("--check", default="all")
    ph.add_argument("--out", default=None, help="write hardened prompt here (default: stdout)")
    ph.add_argument("--write", action="store_true", help="edit the prompt file in place")

    args = p.parse_args(argv)
    if args.cmd == "record":
        return cmd_record(args)
    if args.cmd == "eval":
        return asyncio.run(_eval(args))
    if args.cmd == "prove":
        return asyncio.run(_prove(args))
    if args.cmd == "fix":
        return cmd_fix(args)
    if args.cmd == "harden":
        return cmd_harden(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
