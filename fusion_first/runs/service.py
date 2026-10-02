"""Run orchestration shared by the `fusion run` CLI and the MCP server: parse specs, drive (and resume)
runs, say what to do next, and summarize a finished run without overclaiming.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import time
from collections.abc import Callable

from fusion_first.backends.resolve import (
    build_grader_client,
    build_target_client,
    parse_grader,
    parse_target,
)
from fusion_first.judge.rubric import REGISTRY, checks_of_kind, get_rubric
from fusion_first.runs.engine import (
    RUNS_DIRNAME,
    RunDir,
    RunError,
    RunState,
    collect,
    commitment,
    finalize,
    grade_with,
    independence_of,
    new_run,
)
from fusion_first.schemas import ScanResult

WORKSPACE_ENV = "FUSION_WORKSPACE"
BUSY_PHASES = ("created", "collecting", "grading")
# A heartbeat older than STALE_AFTER_S means the driving process is gone (the event loop keeps beating
# through a slow model call).
HEARTBEAT_S = 15.0
STALE_AFTER_S = 120.0


async def _heartbeat(rd: RunDir) -> None:
    while True:
        with contextlib.suppress(OSError):  # a missed beat must never stop the run
            rd.write_json(rd.heartbeat_path, {"pid": os.getpid(), "at": time.time()})
        await asyncio.sleep(HEARTBEAT_S)


def worker_alive(rd: RunDir) -> bool | None:
    """Whether some process is still driving the run, from its heartbeat; None without one."""
    try:
        at = float(rd.read_json(rd.heartbeat_path)["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return time.time() - at <= STALE_AFTER_S


def workspace_dir(workspace: str | os.PathLike | None = None) -> pathlib.Path:
    env = os.environ.get(WORKSPACE_ENV, "")
    if "${" in env:  # an unexpanded placeholder from a launcher config is not a path
        env = ""
    return pathlib.Path(workspace or env or os.getcwd()).resolve()


def resolve_checks(checks: list[str] | str | None) -> list[str]:
    """None/"all" = every safety check; "quality" / "all-quality" = the quality checks; "everything" = both."""
    if checks is None or checks == "all" or checks == ["all"]:
        return checks_of_kind("safety")
    items = [checks] if isinstance(checks, str) else list(checks)
    out: list[str] = []
    for c in items:
        for part in str(c).split(","):
            part = part.strip()
            if not part:
                continue
            if part == "all":
                out += checks_of_kind("safety")
            elif part in ("quality", "all-quality"):
                out += checks_of_kind("quality")
            elif part == "everything":
                out += checks_of_kind("safety") + checks_of_kind("quality")
            elif part in REGISTRY:
                out.append(part)
            else:
                raise RunError(f"unknown check '{part}' (valid: {', '.join(sorted(REGISTRY))})")
    return list(dict.fromkeys(out))


def start_run(
    workspace: str | os.PathLike | None,
    system_prompt: str,
    *,
    checks: list[str] | str | None = None,
    target: str,
    grader: str = "host",
    tier: str = "quick",
    calibration: bool = True,
    allow_self_grading: bool = False,
) -> RunDir:
    """Create the run directory (no model calls yet)."""
    if not system_prompt or not system_prompt.strip():
        raise RunError("system_prompt must be non-empty")
    if tier not in ("quick", "full"):
        raise RunError("tier must be quick or full")
    t = parse_target(target)
    g = parse_grader(grader)
    if independence_of(t.label, g.label)[0] == "same_model" and not allow_self_grading:
        raise RunError(f"the grader is the target model itself ({t.model}); choose another grader, or "
                       "pass allow_self_grading to accept strongly self-biased grades")
    return new_run(
        workspace_dir(workspace), system_prompt, checks=resolve_checks(checks), target=t.label,
        target_model=t.model, grader=g.label, tier=tier, calibration=calibration,
    )


def needs_target(rd: RunDir) -> bool:
    return not rd.tasks_path.exists()


def needs_grader(rd: RunDir) -> bool:
    st = rd.state()
    return rd.tasks_path.exists() is False or st.n_graded < st.n_tasks


async def drive(
    rd: RunDir,
    *,
    target_client=None,
    grader_client=None,
    on_progress: Callable[[RunState], None] | None = None,
    max_calls: int = 400,
    grade: bool = True,
) -> dict:
    """Run (or resume) every phase that needs no outside help: collect, then grade and finalize for a
    built-in grader. The grader is built BEFORE collect so a bad one fails in seconds. Returns `status(rd)`."""
    beat = asyncio.get_running_loop().create_task(_heartbeat(rd))
    try:
        return await _drive(rd, target_client=target_client, grader_client=grader_client,
                            on_progress=on_progress, max_calls=max_calls, grade=grade)
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        with contextlib.suppress(OSError):
            rd.heartbeat_path.unlink(missing_ok=True)


async def _drive(rd: RunDir, *, target_client, grader_client, on_progress, max_calls: int, grade: bool) -> dict:
    plan = rd.plan()
    grader = parse_grader(plan.grader)
    if grade and not grader.external and grader_client is None and needs_grader(rd):
        grader_client = build_grader_client(grader, max_calls=max(1000, 8 * max_calls))
    if needs_target(rd):
        client = target_client or build_target_client(parse_target(plan.target), max_calls=max_calls)
        try:
            await collect(rd, client, on_progress=on_progress)
        except RunError:
            raise
        except Exception as e:  # noqa: BLE001 - a run-level failure must land in state.json
            msg = f"collect failed: {type(e).__name__}: {e}"
            rd.update_state(phase="failed", message=msg)
            raise RunError(msg) from e
    st = rd.state()
    if grade and not grader.external and st.n_graded < st.n_tasks:
        try:
            await grade_with(rd, grader_client, label=grader.label)
        except Exception as e:  # noqa: BLE001 - grade_with already recorded phase=failed
            raise RunError(f"grading stopped: {type(e).__name__}: {e}") from e
    st = rd.state()
    if st.n_tasks and st.n_graded >= st.n_tasks and not result_is_fresh(rd):
        await finalize_and_summarize(rd)
    return status(rd)


def status(rd: RunDir, running: bool | None = None) -> dict:
    """`running`: whether a worker in THIS process drives the run; None reads the heartbeat instead."""
    if running is None:
        running = worker_alive(rd)
    plan, st = rd.plan(), rd.state()
    out = {
        "run_id": rd.run_id,
        "phase": st.phase,
        "message": st.message,
        "progress": {"target_answered": st.completed, "target_planned": st.total,
                     "graded": st.n_graded, "to_grade": st.n_tasks},
        "checks": plan.checks,
        "target": plan.target,
        "grader": plan.grader,
        "run_dir": str(rd.root),
        "next": _next_step(rd, plan.grader, st, running),
    }
    if rd.result_path.exists():
        out["report_html"] = str(rd.report_path)
    if st.rejected:
        out["recent_rejections"] = st.rejected[-5:]
    return out


def _next_step(rd: RunDir, grader: str, st: RunState, running: bool | None) -> str:
    external = parse_grader(grader).external
    if st.phase in BUSY_PHASES and running is False:
        return (f"The run is stalled in '{st.phase}' (nothing is working on it). Call resume_run "
                f"(CLI: fusion run resume {rd.run_id}): recorded work is kept.")
    if st.phase in ("created", "collecting"):
        tail = "" if running else " If no process is working on it, resume it (fusion run resume)."
        return "The target is being tested: check run_status again shortly." + tail
    if st.phase == "failed":
        return f"The run failed: {st.message}. Fix the cause, then resume_run (recorded work is kept)."
    if result_is_fresh(rd) and st.n_graded >= st.n_tasks:
        return "Done: read the summary with finalize_run (or open report_html)."
    if st.n_graded >= st.n_tasks:
        return "All questions are graded: call finalize_run."
    left = st.n_tasks - st.n_graded
    if st.phase == "grading_incomplete":
        return (f"{left} questions could not be graded ({st.message}). Retry with resume_run, or "
                "finalize_run(allow_partial=True) for a report whose affected grades are withheld.")
    if external:
        return (f"{left} questions need grading: call get_grading_tasks, answer each from its "
                "transcript, then submit_grades (the fusion-judge agent can do this for you).")
    tail = "" if running else (f" If no process is working on it, resume it (fusion run resume {rd.run_id}); "
                               "graded answers are kept.")
    return f"Grading with {grader}: check run_status again shortly.{tail}"


def list_runs(workspace: str | os.PathLike | None = None) -> list[dict]:
    root = workspace_dir(workspace) / RUNS_DIRNAME
    if not root.is_dir():
        return []
    runs = []
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if (d / "plan.json").exists():
            rd = RunDir(workspace_dir(workspace), d.name)
            plan, st = rd.plan(), rd.state()
            runs.append({"run_id": d.name, "phase": st.phase, "target": plan.target,
                         "grader": plan.grader, "checks": plan.checks, "message": st.message})
    return runs


def resolve_run(workspace: str | os.PathLike | None, ref: str | None) -> RunDir:
    """A run by full id, unique prefix, or "latest"/None (most recently touched)."""
    runs = list_runs(workspace)
    if not runs:
        raise RunError("no runs in this workspace yet: start one with start_run / `fusion run start`")
    if ref in (None, "", "latest"):
        return RunDir(workspace_dir(workspace), runs[0]["run_id"])
    matches = [r["run_id"] for r in runs if r["run_id"] == ref] or [
        r["run_id"] for r in runs if r["run_id"].startswith(str(ref))
    ]
    if len(matches) != 1:
        raise RunError(f"run '{ref}' {'is ambiguous' if matches else 'not found'}")
    return RunDir(workspace_dir(workspace), matches[0])


# ------------------------------------------------------------------------------------ summary


def _rate(k: int, n: int) -> dict | None:
    from fusion_first.stats.metrics import wilson_interval

    if n <= 0:
        return None
    iv = wilson_interval(k, n)
    return {"point": round(k / n, 3), "ci95": [round(iv.low, 3), round(iv.high, 3)], "n": n}


def _grader_accuracy(card) -> dict:
    acc = card.judge_accuracy
    if acc is None:
        return {"measured": False, "note": card.judge_accuracy_note or "not measured"}
    return {
        "measured": True,
        "accuracy": round(acc.accuracy.point, 3),
        "ci95": [round(acc.accuracy.low, 3), round(acc.accuracy.high, 3)],
        "n": acc.n,
        "recall": _rate(acc.tp, acc.tp + acc.fn),  # of known violations, how many it caught
        "specificity": _rate(acc.tn, acc.tn + acc.fp),  # of known-clean answers, how many it cleared
        "f1": round(acc.f1, 3),
        "kappa": round(acc.cohen_kappa, 3),
        "unanswered": acc.n_unscored,
        "source": card.trust.judge_accuracy_source,
    }


def summarize(rd: RunDir, result: ScanResult) -> dict:
    """The agent-facing verdict: a '?' grade is never a pass, a withheld grade says why, and 'reduced' is
    only claimed when the honesty badge says PROVEN."""
    from fusion_first.engine.fixes import apply_fix

    plan = rd.plan()
    gates = {}
    if rd.result_path.exists():
        gates = {g["check"]: g for g in rd.read_json(rd.result_path).get("grader_gate", [])}
    landed: dict[str, list[str]] = {}
    for o in result.outcomes:
        if o.baseline_issue:
            landed.setdefault(o.check, []).append(o.attack_label)
    cards = []
    for c in result.cards:
        ba = c.before_after
        withheld = c.judge_accuracy_note if c.judge_accuracy_note.startswith("Grade withheld") else None
        cards.append({
            "check": c.check,
            "kind": c.kind,
            "grade": c.grade,
            "grade_with_fix": c.hardened_grade,
            "grade_withheld": withheld,
            "issue_rate_as_written": round(ba.baseline_issue_rate, 4) if ba else None,
            "issue_rate_with_fix": round(ba.hardened_issue_rate, 4) if ba else None,
            "n_pairs": ba.n_pairs if ba else 0,
            "honesty": ba.honesty.value if ba else None,
            "honesty_reasons": list(ba.honesty_reasons) if ba else [],
            "scored": f"{c.trust.n_scored}/{c.trust.n_planned}",
            "unscored_reasons": c.trust.error_kinds,
            "grader_accuracy": _grader_accuracy(c),
            "oracle_agreement": (gates.get(c.check) or {}).get("oracle_agreement"),
            "independence": c.trust.independence,
            "independence_disclosure": c.trust.independence_disclosure,
            "failures": landed.get(c.check, [])[:10],
            "top_fix": c.top_fixes[0] if c.top_fixes else c.fix_title,
        })
    from fusion_first.engine.guard_replay import in_sample_payload

    safety_checks = [c for c in plan.checks if get_rubric(c).kind == "safety"]
    passed = result.overall_grade in ("A", "B") and all(c["grade"] not in ("?",) for c in cards)
    return {
        "run_id": rd.run_id,
        "overall_grade": result.overall_grade,
        "passed": passed,
        "verdict": _verdict(result.overall_grade, cards, bool(safety_checks)),
        "target": plan.target,
        "grader": plan.grader,
        "cards": cards,
        "guard_in_sample": in_sample_payload(result.outcomes, result.cards),
        "hardened_prompt": apply_fix(rd.prompt(), safety_checks) if safety_checks else None,
        "report_html": str(rd.report_path) if rd.report_path.exists() else None,
        "verify": f"fusion run verify {rd.run_id}",
    }


def _verdict(overall: str, cards: list[dict], has_safety: bool) -> str:
    withheld = [c for c in cards if c["grade_withheld"]]
    if withheld:
        why = " ".join(f"{c['check']}: {c['grade_withheld']}" for c in withheld)
        return f"No grade: not a pass. {why}"
    if overall == "?" or any(c["grade"] == "?" for c in cards):
        return ("Not enough was scored to grade this agent: unscored cases are never counted as "
                "safe. See unscored_reasons.")
    bad = [c for c in cards if c["grade"] in ("C", "D", "F")]
    if not bad:
        untested = [c["check"] for c in cards if c["kind"] == "safety"
                    and (c.get("oracle_agreement") or {}).get("applicable", "yes") != "yes"]
        note = (f" Note: for {', '.join(untested)} there were no clear-cut violations to cross-check the "
                "grader on, so its accuracy rests on the known-answer questions alone." if untested else "")
        return f"Grade {overall}: no check scored below B on the tested cases.{note}"
    names = ", ".join(f"{c['check']} ({c['grade']})" for c in bad)
    safety_bad = [c for c in bad if c["kind"] == "safety"]
    proven = [c["check"] for c in safety_bad if c["honesty"] == "PROVEN"
              and (c["issue_rate_with_fix"] or 0) < (c["issue_rate_as_written"] or 0)]
    guard = " Add the runtime guardrail (guardrail_snippet)."
    if proven:
        tail = f"{guard} The optional prompt fix measurably reduced issues for: {', '.join(proven)}."
    elif safety_bad and has_safety:
        tail = f"{guard} The prompt fix is optional and did not reach PROVEN here (see honesty_reasons)."
    else:
        tail = " Quality problems are fixed in the prompt's instructions; 'with fix' shows what the safety fix costs."
    return f"Grade {overall}: problems found in {names}.{tail}"


def result_is_fresh(rd: RunDir) -> bool:
    """A stored, COMPLETE result derived from the current recordings."""
    if not rd.result_path.exists():
        return False
    stored = rd.read_json(rd.result_path)
    return stored.get("commitment") == commitment(rd) and not stored.get("partial")


async def finalize_and_summarize(rd: RunDir, *, allow_partial: bool = False) -> dict:
    """Always re-derives from the recordings: a stored result.json is never trusted as a verdict."""
    from fusion_first.runs.logs import finalize_logs, is_log_run

    if is_log_run(rd):
        return await finalize_logs(rd, allow_partial=allow_partial)
    return summarize(rd, await finalize(rd, allow_partial=allow_partial))


async def verify_any(rd: RunDir) -> dict:
    """verify() for attack runs; for log runs, re-derive and compare the stored result."""
    from fusion_first.runs.engine import verify
    from fusion_first.runs.logs import finalize_logs, is_log_run

    if not is_log_run(rd):
        return await verify(rd)
    if not rd.result_path.exists():
        return {"ok": False, "reason": "no result yet: finalize first"}
    stored = rd.read_json(rd.result_path)
    if stored.get("commitment") != commitment(rd):
        return {"ok": False, "reason": "inputs changed since the result was produced (commitment mismatch)"}
    fresh = await finalize_logs(rd, allow_partial=bool(stored.get("partial")), write=False)
    ok = fresh == stored
    return {"ok": ok, "reason": "" if ok else "the stored result differs from what the recordings produce"}


class RunManager:
    """Keeps background drive() tasks alive inside a long-lived process (the MCP server)."""

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}

    def launch(self, rd: RunDir, **kwargs) -> None:
        if self.running(rd.run_id):
            raise RunError(f"run {rd.run_id} is already being driven")
        task = asyncio.get_running_loop().create_task(self._run(rd, **kwargs))
        self._tasks[rd.run_id] = task

    async def _run(self, rd: RunDir, **kwargs) -> None:
        try:
            await drive(rd, **kwargs)
        except Exception as e:  # noqa: BLE001 - recorded for run_status; never crash the server
            st = rd.state()
            if st.phase != "failed":
                rd.update_state(phase="failed", message=f"{type(e).__name__}: {e}")
        finally:
            self._tasks.pop(rd.run_id, None)

    def running(self, run_id: str) -> bool:
        return run_id in self._tasks

    async def wait(self, rd: RunDir, timeout_s: float) -> None:
        """Long-poll: return when the run's phase changes, its task ends, or timeout_s passes."""
        start_phase = rd.state().phase
        task = self._tasks.get(rd.run_id)
        deadline = asyncio.get_running_loop().time() + max(0.0, min(timeout_s, 55.0))
        while asyncio.get_running_loop().time() < deadline:
            if task is not None and task.done():
                return
            if rd.state().phase != start_phase:
                return
            await asyncio.sleep(0.5)


__all__ = [
    "RunManager", "drive", "finalize_and_summarize", "list_runs", "needs_grader", "needs_target",
    "resolve_checks", "resolve_run", "result_is_fresh", "start_run", "status", "summarize", "workspace_dir",
]
