"""`fusion run …` and `fusion doctor`: the keyless run engine from a terminal or CI.

    fusion doctor                                             # what can run here (no model calls)
    fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader claude-cli
    fusion run start --prompt agent.txt --target ollama:llama3.2:1b      # grader=host: stops after collect
    fusion run tasks  [RUN] --max 8 > tasks.json              # questions for an external grader
    fusion run submit [RUN] --file answers.json               # validated, one answer per question
    fusion run grade  [RUN]                                   # finish grading with the run's built-in grader
    fusion run finalize [RUN] --min-grade B                   # the card; exit 1 below the bar
    fusion run verify [RUN]                                   # re-derive offline; exit 1 on drift
    fusion run status [RUN] | fusion run list

RUN defaults to the most recent run; a unique id prefix works too.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from fusion_first.backends.resolve import (
    BackendUnavailable,
    SpecError,
    doctor,
    parse_grader,
    parse_target,
)
from fusion_first.errors import FusionError
from fusion_first.runs import service
from fusion_first.runs.engine import RunError, grading_tasks, submit_grades

_GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "?": 5}


def add_parsers(sub) -> None:
    pd = sub.add_parser("doctor", help="show which keyless backends can run here (no model calls)")
    pd.add_argument("--json", action="store_true")
    pd.add_argument("--no-auth-check", action="store_true", help="skip `claude auth status`")

    pr = sub.add_parser("run", help="keyless run engine: collect -> grade -> finalize -> verify")
    rs = pr.add_subparsers(dest="run_cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default=None, help="where .fusion/runs lives (default: cwd)")
    common.add_argument("--json", action="store_true", help="machine-readable output")

    s = rs.add_parser("start", parents=[common], help="create a run and test the target")
    s.add_argument("--prompt", required=True, help="system-prompt file of the agent under test")
    s.add_argument("--check", default="all", help="all | quality | everything | comma list of checks")
    s.add_argument("--target", required=True, help="ollama:<model> | claude-cli:<model> | openai-compat:<url>#<model> | openai:<model> | hf:<model> | anthropic:<model> | openrouter:/together:/groq:/fireworks:/mistral-api:/deepseek:<model> | cmd:<command> (hosted providers need your key and FUSION_ALLOW_API_SPEND=1)")
    s.add_argument("--grader", default="host", help="host | claude-cli[:model] | ollama-prob:<model> | any chat target (openai:<model>, cmd:<command>, ...)")
    s.add_argument("--tier", default="quick", choices=["quick", "full"])
    s.add_argument("--no-calibration", action="store_true", help="skip in-run grader accuracy (not advised)")
    s.add_argument("--collect-only", action="store_true", help="stop after testing the target")
    s.add_argument("--max-calls", type=int, default=400, help="hard cap on target calls")
    s.add_argument("--allow-self-grading", action="store_true", help="let the target model grade itself (biased)")

    p = rs.add_parser("status", parents=[common], help="phase and next step")
    p.add_argument("run", nargs="?", default=None)
    p = rs.add_parser("verify", parents=[common], help="re-derive the result offline")
    p.add_argument("run", nargs="?", default=None)
    p.add_argument("--prompt", default=None, help="also require the run to be of this exact prompt file (CI)")
    rs.add_parser("list", parents=[common], help="runs in this workspace")

    lg = rs.add_parser("logs", parents=[common], help="grade EXISTING agent transcripts (no attacks)")
    lg.add_argument("--file", required=True, help="JSON list or JSON lines: Fusion / OpenAI / Anthropic format")
    lg.add_argument("--check", default="all", help="all | quality | everything | comma list of checks")
    lg.add_argument("--grader", default="host", help="host | claude-cli[:model] | ollama-prob:<model> | any chat target (openai:<model>, cmd:<command>, ...)")
    lg.add_argument("--no-calibration", action="store_true", help="skip grader accuracy (grades withheld)")

    t = rs.add_parser("tasks", parents=[common], help="print ungraded questions (JSON)")
    t.add_argument("run", nargs="?", default=None)
    t.add_argument("--max", type=int, default=8)
    t.add_argument("--lease", type=float, default=None, help="lease seconds (parallel graders)")

    sb = rs.add_parser("submit", parents=[common], help="submit answers (JSON list, file or '-')")
    sb.add_argument("run", nargs="?", default=None)
    sb.add_argument("--file", required=True)
    sb.add_argument("--grader", default="host", help="free-text name of who answered")

    g = rs.add_parser("resume", parents=[common], aliases=["grade"],
                      help="continue a run: finish collecting, grade with its built-in grader, finalize")
    g.add_argument("run", nargs="?", default=None)
    g.add_argument("--max-calls", type=int, default=400, help="hard cap on target calls")

    f = rs.add_parser("finalize", parents=[common], help="build the report card from the recordings")
    f.add_argument("run", nargs="?", default=None)
    f.add_argument("--allow-partial", action="store_true", help="grade '?' where questions are unanswered")
    f.add_argument("--min-grade", default=None, type=str.upper, choices=list("ABCDF"),
                   help="exit 1 if the overall grade is below this (a withheld '?' always fails)")
    f.add_argument("--html", default=None, help="also copy the HTML report here")


def cmd_doctor(args) -> int:
    d = doctor(check_auth=not args.no_auth_check)
    if args.json:
        print(json.dumps(d, indent=2))
        return 0
    b = d["backends"]
    print("Fusion doctor: keyless backends" + (" (FUSION_OFFLINE=1)" if d["offline"] else ""))
    print(f"  claude CLI : {'found' if b['claude_cli']['available'] else 'not found'}"
          f"; subscription auth: {b['claude_cli']['subscription']}")
    models = ", ".join(b["ollama"]["models"]) or "none"
    print(f"  Ollama     : {'running' if b['ollama']['available'] else 'not running'}; models: {models}")
    print("  host agent : grade via MCP (get_grading_tasks / submit_grades)")
    if d["zero_spend"]:
        print("  metered API: disabled (zero spend: True)")
    else:
        print("  metered API: ENABLED (FUSION_ALLOW_API_SPEND=1; hosted presets bill your key)")
    rec = d["recommended"]
    print(f"Recommended: --target {rec['target'] or '<pull a model>'} --grader {rec['grader']}")
    for h in d["hints"]:
        print(f"  hint: {h}")
    return 0


def _out(args, obj, text: str | None = None) -> None:
    if args.json or text is None:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(text)


def _describe_cost(target: str, grader: str) -> str:
    t, g = parse_target(target), parse_grader(grader)
    where = {"ollama": "local model (free)", "claude_cli": "Claude via your CLI subscription (no API key)"}
    gw = {"host": "you / your agent", "claude_cli": "Claude via your CLI subscription (no API key)",
          "ollama_prob": "local probability judge (free)", "ollama_json": "local model (free)"}
    return f"target: {where.get(t.backend, t.backend)} · grader: {gw.get(g.kind, g.kind)}"


async def _start(args) -> int:
    prompt = pathlib.Path(args.prompt).read_text(encoding="utf-8")
    rd = service.start_run(args.workspace, prompt, checks=args.check, target=args.target, grader=args.grader,
                           tier=args.tier, calibration=not args.no_calibration,
                           allow_self_grading=args.allow_self_grading)
    if not args.json:
        print(f"run {rd.run_id} · {_describe_cost(args.target, args.grader)}")

    def progress(st):
        if not args.json:
            print(f"  {st.message}", flush=True)

    st = await service.drive(rd, on_progress=progress, max_calls=args.max_calls, grade=not args.collect_only)
    if rd.result_path.exists():
        return _print_summary(args, await service.finalize_and_summarize(rd))
    _out(args, st, f"{st['phase']}: {st['next']}")
    return 0


def _print_summary(args, summary: dict, min_grade: str | None = None) -> int:
    lines = [f"Overall grade {summary['overall_grade']}: {summary['verdict']}"]
    for c in summary["cards"]:
        if c.get("grade_withheld"):
            lines.append(f"  {c['check']}: {c['grade_withheld']}")
        acc = c["grader_accuracy"]
        acc_s = (f"grader accuracy {acc['accuracy']:.0%} (95% CI {acc['ci95'][0]:.0%}–{acc['ci95'][1]:.0%},"
                 f" n={acc['n']})" if "accuracy" in acc else f"grader accuracy: {acc['note']}")
        rate = c["issue_rate_as_written"]
        rate_s = "n/a" if rate is None else f"{rate:.0%} → {c['issue_rate_with_fix']:.0%} with fix"
        lines.append(f"  {c['check']:26} {c['grade']}  issues {rate_s} [{c['honesty']}] "
                     f"scored {c['scored']} · {acc_s}")
    if summary.get("guard_in_sample"):
        lines.append(f"{summary['guard_in_sample']['sentence']} {summary['guard_in_sample']['setup']}")
    if summary.get("report_html"):
        lines.append(f"Report: {summary['report_html']}")
    lines.append(f"Verify: {summary['verify']}")
    _out(args, summary, "\n".join(lines))
    if min_grade and _GRADE_RANK.get(summary["overall_grade"], 5) > _GRADE_RANK[min_grade.upper()]:
        return 1  # a withheld '?' ranks below F: it fails every bar
    return 0


async def _resume(args, rd) -> int:
    st = await service.drive(rd, max_calls=args.max_calls)
    if rd.result_path.exists() and service.result_is_fresh(rd):
        from fusion_first.runs.logs import is_log_run

        summary = await service.finalize_and_summarize(rd)
        return _print_logs_summary(args, summary) if is_log_run(rd) else _print_summary(args, summary)
    if parse_grader(rd.plan().grader).external and st["phase"] == "awaiting_grades":
        st["next"] += " (CLI: fusion run tasks / fusion run submit)"
    _out(args, st, f"{st['phase']}: {st['next']}")
    return 0


async def _logs(args) -> int:
    from fusion_first.runs.logs import new_log_run, parse_transcripts

    g = parse_grader(args.grader)
    grader_client = None
    if not g.external:
        from fusion_first.backends.resolve import build_grader_client

        grader_client = build_grader_client(g)  # pre-flight before any work
    transcripts = parse_transcripts(pathlib.Path(args.file).read_text(encoding="utf-8"))
    rd = await new_log_run(service.workspace_dir(args.workspace), transcripts,
                           checks=service.resolve_checks(args.check), grader=g.label,
                           calibration=not args.no_calibration)
    if not args.json:
        print(f"run {rd.run_id}: {len(transcripts)} transcripts, {rd.state().n_tasks} questions")
    st = await service.drive(rd, grader_client=grader_client)
    if st["phase"] == "done":
        return _print_logs_summary(args, await service.finalize_and_summarize(rd))
    if g.external:
        st["next"] += " (CLI: fusion run tasks / fusion run submit, then fusion run finalize)"
    _out(args, st, f"{st['phase']}: {st['next']}")
    return 0


def _print_logs_summary(args, res: dict, min_grade: str | None = None) -> int:
    lines = [f"Overall grade {res['overall_grade']} over graded transcripts"]
    for check, c in res["checks"].items():
        iv = c["issue_rate"]
        lines.append(f"  {check:26} {c['grade']}  {c['flagged']}/{c['n_transcripts']} flagged "
                     f"({iv['point']:.0%}, 95% CI {iv['ci95'][0]:.0%}–{iv['ci95'][1]:.0%})")
        if c["grade_withheld"]:
            lines.append(f"    {c['grade_withheld']}")
    _out(args, res, "\n".join(lines))
    if min_grade and _GRADE_RANK.get(res["overall_grade"], 5) > _GRADE_RANK[min_grade.upper()]:
        return 1
    return 0


async def _finalize(args, rd) -> int:
    from fusion_first.runs.logs import is_log_run

    if is_log_run(rd):
        return _print_logs_summary(args, await service.finalize_and_summarize(
            rd, allow_partial=args.allow_partial), args.min_grade)
    summary = await service.finalize_and_summarize(rd, allow_partial=args.allow_partial)
    if args.html and rd.report_path.exists():
        pathlib.Path(args.html).write_text(rd.report_path.read_text(encoding="utf-8"), encoding="utf-8")
    return _print_summary(args, summary, args.min_grade)


def _read_answers(path: str) -> list[dict]:
    raw = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("grades", [data])
    if not isinstance(data, list):
        raise RunError("answers must be a JSON list of {task_id, criteria, rationale, confidence}")
    return data


def cmd_run(args) -> int:
    try:
        if args.run_cmd == "start":
            return asyncio.run(_start(args))
        if args.run_cmd == "logs":
            return asyncio.run(_logs(args))
        if args.run_cmd == "list":
            runs = service.list_runs(args.workspace)
            _out(args, runs, "\n".join(f"{r['run_id']}  {r['phase']:16} {r['target']}  grader={r['grader']}"
                                        for r in runs) or "no runs yet")
            return 0
        rd = service.resolve_run(args.workspace, args.run)
        if args.run_cmd == "status":
            st = service.status(rd)
            _out(args, st, f"{rd.run_id}: {st['phase']}: {st['next']}")
            return 0
        if args.run_cmd == "tasks":
            print(json.dumps(grading_tasks(rd, max_tasks=args.max, lease_s=args.lease), indent=2,
                             ensure_ascii=False))
            return 0
        if args.run_cmd == "submit":
            res = submit_grades(rd, _read_answers(args.file), grader=args.grader)
            _out(args, res)
            return 0 if not res["rejected"] else 3
        if args.run_cmd in ("resume", "grade"):
            return asyncio.run(_resume(args, rd))
        if args.run_cmd == "finalize":
            return asyncio.run(_finalize(args, rd))
        if args.run_cmd == "verify":
            if args.prompt:
                import hashlib

                current = hashlib.sha256(pathlib.Path(args.prompt).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                if current != rd.plan().prompt_sha256:
                    res = {"ok": False, "reason": f"{args.prompt} changed since run {rd.run_id} tested it: re-run"}
                    _out(args, res, f"FAILED: {res['reason']}")
                    return 1
            res = asyncio.run(service.verify_any(rd))
            _out(args, res, "verified: result re-derived exactly (in-sample guard verdicts excluded)" if res["ok"] else f"FAILED: {res['reason']}")
            return 0 if res["ok"] else 1
    except (RunError, SpecError, BackendUnavailable, FusionError, ValueError, OSError) as e:
        # exit 2 = the run could not proceed; exit 1 is reserved for a failed gate or verify drift
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 2
