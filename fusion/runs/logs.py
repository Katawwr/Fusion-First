"""Grade EXISTING agent transcripts ("bring your logs") — no attacks, no API key.

Teams already have logs of their agent talking to real users and tools. This turns each transcript
into the production judge's questions for the chosen checks (safety and/or quality), mixes in the
blind known-answer questions for the same checks, and lets any keyless grader answer them through
the run engine (host agent via MCP / `fusion run tasks|submit`, or a built-in grader). The result is
the issue rate per check with a Wilson interval, the flagged transcripts with the agent's own words
as evidence, and the grader's measured accuracy — with the rate's grade withheld when the grader
doesn't clear the policy floor, exactly as for attack runs.

Accepted formats (a JSON list, or one JSON object per line):
  Fusion      {"id": ..., "steps": [{"role": ..., "content": ..., "tool_call": ..., "tool_result": ...}]}
  OpenAI      {"id": ..., "messages": [{"role": "system|user|assistant|tool", "content": ..., "tool_calls": [...]}]}
  Anthropic   {"id": ..., "system": "...", "messages": [{"role": ..., "content": "..." | [blocks]}]}
Tool results in logs are treated as untrusted data (fenced), since the grader must never take
instructions from them.
"""

from __future__ import annotations

import dataclasses
import json
import os

from fusion.judge.judge import Judge, JudgeParseError
from fusion.judge.rubric import REGISTRY, get_rubric
from fusion.runs.engine import (
    CollectingJudgeClient,
    RunDir,
    RunError,
    Task,
    _check_of,
    _JudgeReplay,
    _snapshot,
    _task_id,
    _validate_recorded_answers,
    new_run,
)
from fusion.schemas import Role, Step, ToolCall, ToolResult, Trajectory

MAX_TRANSCRIPTS = 2000


# ------------------------------------------------------------------------------------ parsing


def _text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") in (None, "text", "output_text", "input_text"):
                    parts.append(str(b.get("text", "")))
                elif b.get("type") == "tool_result":
                    parts.append(_text(b.get("content")))
            else:
                parts.append(str(b))
        return "\n".join(p for p in parts if p)
    return str(content)


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        return {"raw": raw}
    return val if isinstance(val, dict) else {"value": val}


def _from_openai(messages: list[dict]) -> list[Step]:
    steps: list[Step] = []
    for m in messages:
        role = m.get("role")
        if role in ("system", "developer"):
            steps.append(Step(role=Role.SYSTEM, content=_text(m.get("content"))))
        elif role == "user":
            steps.append(Step(role=Role.USER, content=_text(m.get("content"))))
        elif role == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or tc
                steps.append(Step(role=Role.ASSISTANT, tool_call=ToolCall(
                    name=str(fn.get("name", "tool")), arguments=_args(fn.get("arguments")))))
            text = _text(m.get("content"))
            if text:
                steps.append(Step(role=Role.ASSISTANT, content=text))
        elif role in ("tool", "function"):
            steps.append(Step(role=Role.TOOL, tool_result=ToolResult(
                tool=str(m.get("name") or m.get("tool_call_id") or "tool"), content=_text(m.get("content")),
                injected=True)))
    return steps


def _from_anthropic(system, messages: list[dict]) -> list[Step]:
    steps: list[Step] = []
    if system:
        steps.append(Step(role=Role.SYSTEM, content=_text(system)))
    for m in messages:
        role, content = m.get("role"), m.get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": _text(content)}]
        for b in blocks:
            if not isinstance(b, dict):
                continue
            kind = b.get("type")
            if kind == "tool_use":
                steps.append(Step(role=Role.ASSISTANT, tool_call=ToolCall(
                    name=str(b.get("name", "tool")), arguments=_args(b.get("input")))))
            elif kind == "tool_result":
                steps.append(Step(role=Role.TOOL, tool_result=ToolResult(
                    tool=str(b.get("tool_use_id", "tool")), content=_text(b.get("content")), injected=True)))
            elif kind in (None, "text") and _text(b.get("text")):
                steps.append(Step(role=Role.ASSISTANT if role == "assistant" else Role.USER,
                                  content=_text(b.get("text"))))
    return steps


def parse_transcripts(text: str) -> list[tuple[str, Trajectory]]:
    """Parse a JSON list or JSON lines of transcripts in any supported format."""
    text = text.strip()
    if not text:
        raise RunError("no transcripts in the input")
    try:
        data = json.loads(text)
        records = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(records) > MAX_TRANSCRIPTS:
        raise RunError(f"at most {MAX_TRANSCRIPTS} transcripts per run (got {len(records)})")
    out: list[tuple[str, Trajectory]] = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise RunError(f"transcript {i} is not a JSON object")
        tid = str(r.get("id") or f"t{i + 1}")
        if "steps" in r:
            traj = Trajectory.model_validate({"steps": r["steps"]})
        elif "messages" in r and "system" in r:
            traj = Trajectory(steps=_from_anthropic(r.get("system"), r["messages"]))
        elif "messages" in r:
            traj = Trajectory(steps=_from_openai(r["messages"]))
        else:
            raise RunError(f"transcript {tid}: expected 'steps' or 'messages'")
        if not any(s.role == Role.ASSISTANT for s in traj.steps):
            raise RunError(f"transcript {tid} has no assistant turn to grade")
        out.append((tid, traj))
    ids = [t for t, _ in out]
    if len(set(ids)) != len(ids):
        raise RunError("transcript ids must be unique")
    return out


# ------------------------------------------------------------------------------------ run


async def new_log_run(
    workspace: str | os.PathLike,
    transcripts: list[tuple[str, Trajectory]],
    *,
    checks: list[str],
    grader: str,
    calibration: bool = True,
    run_id: str | None = None,
) -> RunDir:
    """Create a run whose questions are the transcripts' judge questions (+ known-answer questions)."""
    from fusion.goldset import load_gold
    from fusion.stats.calibration import run_calibration

    unknown = [c for c in checks if c not in REGISTRY]
    if unknown:
        raise RunError(f"unknown checks: {unknown}")
    manifest = json.dumps([{"id": t, "steps": len(tr.steps)} for t, tr in transcripts], sort_keys=True)
    rd = new_run(workspace, f"logs:{manifest}", checks=list(checks), target="ollama:logs",
                 target_model="logs", grader=grader, calibration=calibration, run_id=run_id)
    rd.write_json(rd.root / "transcripts.json", [{"id": t, **tr.model_dump(mode="json")} for t, tr in transcripts])
    collector = CollectingJudgeClient()
    items: dict[str, dict] = {}
    for tid, traj in transcripts:
        for check in checks:
            req = Judge(None)._build_request(traj, get_rubric(check))
            collector.requests[req.cache_key()] = req
            items.setdefault(req.cache_key(), {"transcript": tid, "check": check})
    if calibration:
        for check in checks:
            if any(c.split == "blind" for c in load_gold(check)):
                await run_calibration(check, collector, split="blind")
    secret = rd.secret_path.read_text(encoding="utf-8").strip()
    tasks = sorted((Task(_task_id(secret, k), _check_of(r), k) for k, r in collector.requests.items()),
                   key=lambda t: t.task_id)
    rd.write_json(rd.tasks_path, [dataclasses.asdict(t) for t in tasks])
    rd.write_json(rd.requests_path, {k: r.model_dump(mode="json") for k, r in collector.requests.items()})
    rd.write_json(rd.root / "items.json", items)
    rd.update_state(phase="awaiting_grades", n_tasks=len(tasks), n_graded=0,
                    message=f"{len(tasks)} questions to grade ({len(transcripts)} transcripts x {len(checks)} checks)")
    return rd


def is_log_run(rd: RunDir) -> bool:
    return (rd.root / "items.json").exists() and (rd.root / "transcripts.json").exists()


async def finalize_logs(rd: RunDir, *, allow_partial: bool = False, write: bool = True) -> dict:
    """Issue rate per check (Wilson), flagged transcripts, grader accuracy, and the same grade gate
    as attack runs (withheld when the grader didn't earn it)."""

    from fusion.judge.judge import judge_prompt_version

    snap = _snapshot(rd)
    with judge_prompt_version(snap.plan.judge_prompt_version):
        return await _finalize_logs(rd, snap, allow_partial, write)


async def _finalize_logs(rd: RunDir, snap, allow_partial: bool, write: bool) -> dict:
    from fusion.engine.report import grade_for_rate
    from fusion.stats.calibration import run_calibration
    from fusion.stats.gate import load_policy
    from fusion.stats.metrics import wilson_interval

    graded = [t for t in rd.tasks() if t.key in snap.judge.entries]
    if len(graded) < snap.n_tasks and not allow_partial:
        raise RunError(f"{snap.n_tasks - len(graded)} questions are still ungraded")
    _validate_recorded_answers(rd, snap)
    items = rd.read_json(rd.root / "items.json")
    plan = snap.plan
    checks_out = {}
    for check in plan.checks:
        rubric = get_rubric(check)
        flagged, n, ungraded = [], 0, 0
        for key, meta in items.items():
            if meta["check"] != check:
                continue
            entry = snap.judge.entries.get(key)
            if entry is None:
                ungraded += 1
                continue
            try:
                v = Judge._parse(str(entry["text"]), rubric, str(entry.get("model", "")))
            except JudgeParseError:
                ungraded += 1
                continue
            n += 1
            if v.is_issue:
                flagged.append({"transcript": meta["transcript"],
                                "criteria": [c.id for c in v.criteria if c.violated],
                                "evidence": [c.evidence for c in v.criteria if c.violated][:3],
                                "rationale": v.rationale[:300]})
        rate = wilson_interval(len(flagged), n)
        reasons = []
        if ungraded:
            reasons.append(f"{ungraded} transcript(s) were never graded")
        acc = None
        if plan.calibration:
            try:
                outcome = await run_calibration(check, _JudgeReplay(snap.judge, allow_partial), split="blind")
                acc = outcome.result
            except Exception as e:  # noqa: BLE001 - reported as unmeasured, never guessed
                reasons.append(f"the grader's accuracy could not be measured ({type(e).__name__})")
        else:
            reasons.append("in-run calibration was switched off, so the grader's accuracy is unmeasured")
        policy = load_policy(check)
        if acc is not None:
            if acc.n_unscored:
                reasons.append(f"the grader left {acc.n_unscored} known-answer question(s) unanswered")
            if acc.f1 < policy["min_judge_f1"]:
                reasons.append(f"grader F1 {acc.f1:.2f} on known-answer questions is below the floor "
                               f"{policy['min_judge_f1']:.2f}")
            if acc.accuracy.point < policy["min_judge_accuracy"]:
                reasons.append(f"grader accuracy {acc.accuracy.point:.2f} is below the floor "
                               f"{policy['min_judge_accuracy']:.2f}")
        grade = "?" if (reasons or n == 0) else grade_for_rate(len(flagged) / n)
        checks_out[check] = {
            "kind": rubric.kind, "n_transcripts": n, "flagged": len(flagged),
            "issue_rate": {"point": round(rate.point, 4), "ci95": [round(rate.low, 4), round(rate.high, 4)]},
            "grade": grade, "grade_withheld": ("Grade withheld: " + "; ".join(reasons) + ".") if reasons else None,
            "grader_accuracy": ({"accuracy": round(acc.accuracy.point, 3),
                                 "ci95": [round(acc.accuracy.low, 3), round(acc.accuracy.high, 3)],
                                 "n": acc.n, "f1": round(acc.f1, 3)} if acc else None),
            "flagged_transcripts": flagged[:50],
        }
    grades = [c["grade"] for c in checks_out.values()]
    rank = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "?": 5}
    overall = max(grades, key=lambda g: rank.get(g, 5)) if grades else "?"
    result = {"kind": "logs", "run_id": rd.run_id, "grader": plan.grader, "overall_grade": overall,
              "passed": overall in ("A", "B"), "checks": checks_out,
              "partial": len(graded) < snap.n_tasks, "commitment": snap.commitment}
    if write:
        with rd.lock():
            rd.write_json(rd.result_path, result)
            st = rd.state()
            if not result["partial"]:
                st.phase, st.message = "done", f"overall grade {overall}"
            rd.save_state(st)
    return result
