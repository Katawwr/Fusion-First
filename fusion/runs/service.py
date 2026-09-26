"""Run orchestration shared by the `fusion run` CLI and the MCP server.

The engine (`fusion.runs.engine`) knows phases; this module knows USERS: it parses target/grader
specs, drives collect -> grade -> finalize for built-in graders, tells an agent what to do next, and
summarizes a finished run in plain, honest language (grade, what got through, how sure we are, and
how accurate the grader was measured to be in this very run).
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from collections.abc import Callable
from dataclasses import asdict

from fusion.backends.resolve import (
    GraderSpec,
    build_grader_client,
    build_target_client,
    parse_grader,
    parse_target,
)
from fusion.judge.rubric import REGISTRY, checks_of_kind, get_rubric
from fusion.runs.engine import (
    RUNS_DIRNAME,
    RunDir,
    RunError,
    RunState,
    collect,
    commitment,
    finalize,
    grade_with,
    new_run,
)
from fusion.schemas import ScanResult

WORKSPACE_ENV = "FUSION_WORKSPACE"


def workspace_dir(workspace: str | os.PathLike | None = None) -> pathlib.Path:
    return pathlib.Path(workspace or os.environ.get(WORKSPACE_ENV) or os.getcwd()).resolve()


def resolve_checks(checks: list[str] | str | None) -> list[str]:
    """None/"all" = every safety check; "quality" / "all-quality" = the quality checks; "everything" =
    both. Unknown names are rejected with the valid list."""
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
) -> RunDir:
    """Create the run directory (no model calls yet)."""
    if not system_prompt or not system_prompt.strip():
        raise RunError("system_prompt must be non-empty")
    if tier not in ("quick", "full"):
        raise RunError("tier must be quick or full")
    t = parse_target(target)
    g = parse_grader(grader)
    return new_run(
        workspace_dir(workspace), system_prompt, checks=resolve_checks(checks), target=t.label,
        target_model=t.model, grader=g.label, tier=tier, calibration=calibration,
    )


async def drive(
    rd: RunDir,
    *,
    target_client=None,
    grader_client=None,
    on_progress: Callable[[RunState], None] | None = None,
    max_calls: int = 400,
    grade: bool = True,
) -> dict:
    """Run every phase that needs no outside help: collect, then (for a built-in grader) grade and
    finalize. Clients are built from the plan when not injected. Returns `status(rd)`."""
    plan = rd.plan()
    grader = parse_grader(plan.grader)
    st = rd.state()
    if st.phase in ("created", "collecting", "failed") and not rd.tasks_path.exists():
        client = target_client or build_target_client(parse_target(plan.target), max_calls=max_calls)
        try:
            await collect(rd, client, on_progress=on_progress)
        except RunError:
            raise
        except Exception as e:  # noqa: BLE001 - a run-level failure must land in state.json
            st = rd.state()
            st.phase, st.message = "failed", f"collect failed: {type(e).__name__}: {e}"
            rd.save_state(st)
            raise RunError(st.message) from e
    if grade and not grader.external and rd.state().n_graded < rd.state().n_tasks:
        client = grader_client or build_grader_client(grader, max_calls=max(1000, 4 * rd.state().n_tasks))
        st = rd.state()
        st.phase, st.message = "grading", f"grading with {grader.label}"
        rd.save_state(st)
        await grade_with(rd, client, label=grader.label)
    st = rd.state()
    if st.n_tasks and st.n_graded >= st.n_tasks and not result_is_fresh(rd):
        await finalize(rd)
    return status(rd)


def status(rd: RunDir) -> dict:
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
        "next": _next_step(rd, plan.grader, st),
    }
    if rd.result_path.exists():
        out["report_html"] = str(rd.report_path)
    if st.rejected:
        out["recent_rejections"] = st.rejected[-5:]
    return out


def _next_step(rd: RunDir, grader: str, st: RunState) -> str:
    if st.phase in ("created", "collecting"):
        return "The target is being tested — check run_status again shortly."
    if st.phase == "failed":
        return f"The run failed: {st.message}"
    if result_is_fresh(rd) and st.n_graded >= st.n_tasks:
        return "Done — read the summary with finalize_run (or open report_html)."
    if st.n_graded >= st.n_tasks:
        return "All questions are graded — call finalize_run."
    if parse_grader(grader).external:
        left = st.n_tasks - st.n_graded
        return (f"{left} questions need grading: call get_grading_tasks, answer each from its "
                "transcript, then submit_grades (the fusion-judge agent can do this for you).")
    return f"Grading with {grader} — check run_status again shortly."


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
        raise RunError("no runs in this workspace yet — start one with start_run / `fusion run start`")
    if ref in (None, "", "latest"):
        return RunDir(workspace_dir(workspace), runs[0]["run_id"])
    matches = [r["run_id"] for r in runs if r["run_id"] == ref] or [
        r["run_id"] for r in runs if r["run_id"].startswith(str(ref))
    ]
    if len(matches) != 1:
        raise RunError(f"run '{ref}' {'is ambiguous' if matches else 'not found'}")
    return RunDir(workspace_dir(workspace), matches[0])


# ------------------------------------------------------------------------------------ summary


def summarize(rd: RunDir, result: ScanResult) -> dict:
    """The agent-facing verdict. States only what the numbers support: a '?' grade is never a pass,
    and a reduction is only called proven when the honesty badge says PROVEN."""
    from fusion.engine.fixes import apply_fix

    plan = rd.plan()
    landed: dict[str, list[str]] = {}
    for o in result.outcomes:
        if o.baseline_issue:
            landed.setdefault(o.check, []).append(o.attack_label)
    cards = []
    for c in result.cards:
        ba, acc = c.before_after, c.judge_accuracy
        cards.append({
            "check": c.check,
            "kind": c.kind,
            "grade": c.grade,
            "grade_with_fix": c.hardened_grade,
            "issue_rate_as_written": round(ba.baseline_issue_rate, 4) if ba else None,
            "issue_rate_with_fix": round(ba.hardened_issue_rate, 4) if ba else None,
            "n_pairs": ba.n_pairs if ba else 0,
            "honesty": ba.honesty.value if ba else None,
            "honesty_reasons": list(ba.honesty_reasons) if ba else [],
            "scored": f"{c.trust.n_scored}/{c.trust.n_planned}",
            "unscored_reasons": c.trust.error_kinds,
            "grader_accuracy": (
                {"accuracy": round(acc.accuracy.point, 3), "ci95": [round(acc.accuracy.low, 3),
                 round(acc.accuracy.high, 3)], "n": acc.n, "source": c.trust.judge_accuracy_source}
                if acc else {"note": c.judge_accuracy_note or "not measured"}
            ),
            "failures": landed.get(c.check, [])[:10],
            "top_fix": c.top_fixes[0] if c.top_fixes else c.fix_title,
        })
    safety_checks = [c for c in plan.checks if get_rubric(c).kind == "safety"]
    return {
        "run_id": rd.run_id,
        "overall_grade": result.overall_grade,
        "passed": result.overall_grade in ("A", "B") and all(c["grade"] != "?" for c in cards),
        "verdict": _verdict(result.overall_grade, cards),
        "target": plan.target,
        "grader": plan.grader,
        "cards": cards,
        "hardened_prompt": apply_fix(rd.prompt(), safety_checks) if safety_checks else None,
        "report_html": str(rd.report_path) if rd.report_path.exists() else None,
        "verify": f"fusion run verify {rd.run_id}",
    }


def _verdict(overall: str, cards: list[dict]) -> str:
    if overall == "?" or any(c["grade"] == "?" for c in cards):
        return ("Not enough was scored to grade this agent — unscored cases are never counted as "
                "safe. See unscored_reasons.")
    bad = [c for c in cards if c["grade"] in ("C", "D", "F")]
    if not bad:
        return f"Grade {overall}: no check scored below B on the tested cases."
    names = ", ".join(f"{c['check']} ({c['grade']})" for c in bad)
    proven = [c["check"] for c in bad if c["honesty"] == "PROVEN"
              and (c["issue_rate_with_fix"] or 0) < (c["issue_rate_as_written"] or 0)]
    tail = (f" The fix measurably reduced issues for: {', '.join(proven)}." if proven else
            " Apply hardened_prompt and re-run to measure the fix (sample too small to call it proven).")
    return f"Grade {overall}: problems found in {names}.{tail}"


def result_is_fresh(rd: RunDir) -> bool:
    """A stored result counts only if it was derived from the CURRENT recordings (a partial result
    finalized before the last answers arrived is stale)."""
    if not rd.result_path.exists():
        return False
    return rd.read_json(rd.result_path).get("commitment") == commitment(rd)


async def finalize_and_summarize(rd: RunDir, *, allow_partial: bool = False) -> dict:
    if result_is_fresh(rd) and not allow_partial:
        result = ScanResult.model_validate(
            {k: v for k, v in rd.read_json(rd.result_path).items() if k in ScanResult.model_fields}
        )
    else:
        result = await finalize(rd, allow_partial=allow_partial)
    return summarize(rd, result)


class RunManager:
    """Keeps background drive() tasks alive inside a long-lived process (the MCP server)."""

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}

    def launch(self, rd: RunDir, **kwargs) -> None:
        task = asyncio.get_running_loop().create_task(self._run(rd, **kwargs))
        self._tasks[rd.run_id] = task

    async def _run(self, rd: RunDir, **kwargs) -> None:
        try:
            await drive(rd, **kwargs)
        except Exception as e:  # noqa: BLE001 - recorded for run_status; never crash the server
            st = rd.state()
            if st.phase != "failed":
                st.phase, st.message = "failed", f"{type(e).__name__}: {e}"
                rd.save_state(st)
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


def plan_dict(rd: RunDir) -> dict:
    return asdict(rd.plan())


__all__ = [
    "GraderSpec", "RunManager", "drive", "finalize_and_summarize", "list_runs", "plan_dict",
    "resolve_checks", "resolve_run", "start_run", "status", "summarize", "workspace_dir",
]
