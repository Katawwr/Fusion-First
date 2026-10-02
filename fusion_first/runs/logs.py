"""Grade EXISTING agent transcripts ("bring your logs"): no attacks, no API key.

Each transcript becomes the judge's questions for the chosen checks, mixed with the blind known-answer
questions, and any grader answers them through the run engine. The result is the issue rate per check
(Wilson interval), the flagged transcripts, and the grader's measured accuracy. Grades are withheld as
for attack runs, and also when there are too few transcripts.

Accepted formats (a JSON list, or one JSON object per line):
  Fusion      {"id": ..., "steps": [{"role": ..., "content": ..., "tool_call": ..., "tool_result": ...}]}
  OpenAI      {"id": ..., "messages": [{"role": "system|developer|user|assistant|tool|function", ...}]}
              (assistant tool_calls, legacy function_call, and Responses-API function_call /
              function_call_output items are all kept)
  Anthropic   {"id": ..., "system": "...", "messages": [{"role": ..., "content": "..." | [blocks]}]}
              (detected by typed content blocks; "system" is optional)
Every tool result is untrusted data (fenced), since the grader must never take instructions from it.
Transcripts longer than the judge's evidence window are graded in windows: flagged if any window is.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os

from fusion_first.judge.judge import (
    DEFAULT_EVIDENCE_CHARS,
    Judge,
    JudgeParseError,
    _fence_untrusted,
)
from fusion_first.judge.rubric import REGISTRY, get_rubric
from fusion_first.runs.engine import (
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
from fusion_first.schemas import Role, Step, ToolCall, ToolResult, Trajectory

MAX_TRANSCRIPTS = 2000
MAX_INPUT_BYTES = 50_000_000
MIN_TRANSCRIPTS_FOR_GRADE = 10
WINDOW_CHARS = int(DEFAULT_EVIDENCE_CHARS * 0.85)  # leave room for the pinned system/user head


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
    if isinstance(content, dict):
        return _text(content.get("text") or content.get("content"))
    return str(content)


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        return {"raw": raw}
    return val if isinstance(val, dict) else {"value": val}


def _tool_result(name, content) -> Step:
    return Step(role=Role.TOOL, tool_result=ToolResult(tool=str(name or "tool"), content=_text(content), injected=True))


def _from_openai(messages: list) -> list[Step]:
    steps: list[Step] = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            raise RunError(f"message {i} is not a JSON object")
        role, kind = m.get("role"), m.get("type")
        if kind == "function_call":  # Responses API
            steps.append(Step(role=Role.ASSISTANT, tool_call=ToolCall(name=str(m.get("name", "tool")),
                                                                    arguments=_args(m.get("arguments")))))
        elif kind == "function_call_output":
            steps.append(_tool_result(m.get("call_id") or m.get("name"), m.get("output")))
        elif role in ("system", "developer"):
            steps.append(Step(role=Role.SYSTEM, content=_text(m.get("content"))))
        elif role == "user":
            steps.append(Step(role=Role.USER, content=_text(m.get("content"))))
        elif role == "assistant":
            calls = list(m.get("tool_calls") or [])
            if m.get("function_call"):  # legacy
                calls.append({"function": m["function_call"]})
            for tc in calls:
                fn = tc.get("function") or tc
                steps.append(Step(role=Role.ASSISTANT, tool_call=ToolCall(
                    name=str(fn.get("name", "tool")), arguments=_args(fn.get("arguments")))))
            text = _text(m.get("content"))
            if text:
                steps.append(Step(role=Role.ASSISTANT, content=text))
        elif role in ("tool", "function"):
            steps.append(_tool_result(m.get("name") or m.get("tool_call_id"), m.get("content")))
        elif kind == "message":  # Responses API message item without a chat role we know
            steps.append(Step(role=Role.ASSISTANT, content=_text(m.get("content"))))
        else:
            raise RunError(f"message {i}: unsupported role/type {role or kind!r}")
    return steps


def _from_anthropic(system, messages: list) -> list[Step]:
    steps: list[Step] = []
    if system:
        steps.append(Step(role=Role.SYSTEM, content=_text(system)))
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            raise RunError(f"message {i} is not a JSON object")
        role, content = m.get("role"), m.get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": _text(content)}]
        for b in blocks:
            if isinstance(b, str):
                b = {"type": "text", "text": b}
            if not isinstance(b, dict):
                raise RunError(f"message {i}: content blocks must be objects")
            kind = b.get("type")
            if kind == "tool_use":
                steps.append(Step(role=Role.ASSISTANT, tool_call=ToolCall(
                    name=str(b.get("name", "tool")), arguments=_args(b.get("input")))))
            elif kind == "tool_result":
                steps.append(_tool_result(b.get("tool_use_id"), b.get("content")))
            elif kind in (None, "text"):
                if _text(b.get("text")):
                    steps.append(Step(role=Role.ASSISTANT if role == "assistant" else Role.USER,
                                      content=_text(b.get("text"))))
            elif kind in ("thinking", "redacted_thinking", "image", "document"):
                continue
            else:
                raise RunError(f"message {i}: unsupported content block {kind!r}")
    return steps


def _anthropic_shaped(messages: list) -> bool:
    return any(isinstance(m, dict) and isinstance(m.get("content"), list)
               and any(isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result") for b in m["content"])
               for m in messages)


def parse_transcripts(text: str) -> list[tuple[str, Trajectory]]:
    """Parse a JSON list or JSON lines of transcripts in any supported format."""
    if len(text.encode("utf-8", "ignore")) > MAX_INPUT_BYTES:
        raise RunError(f"input larger than {MAX_INPUT_BYTES // 1_000_000} MB: split it into several runs")
    text = text.strip()
    if not text:
        raise RunError("no transcripts in the input")
    try:
        data = json.loads(text)
        records = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        try:
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as e:
            raise RunError(f"input is neither JSON nor JSON lines: {e}") from e
    if len(records) > MAX_TRANSCRIPTS:
        raise RunError(f"at most {MAX_TRANSCRIPTS} transcripts per run (got {len(records)})")
    out: list[tuple[str, Trajectory]] = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise RunError(f"transcript {i} is not a JSON object")
        tid = str(r.get("id") or f"t{i + 1}")
        if "steps" in r:
            try:
                traj = Trajectory.model_validate({"steps": r["steps"]})
            except Exception as e:  # noqa: BLE001 - pydantic detail is shown to the user
                raise RunError(f"transcript {tid}: {e}") from e
            for s in traj.steps:  # tool output in logs is untrusted, whatever the file claims
                if s.tool_result is not None:
                    s.tool_result.injected = True
        elif isinstance(r.get("messages"), list):
            msgs = r["messages"]
            if "system" in r or _anthropic_shaped(msgs):
                traj = Trajectory(steps=_from_anthropic(r.get("system"), msgs))
            else:
                traj = Trajectory(steps=_from_openai(msgs))
        else:
            raise RunError(f"transcript {tid}: expected 'steps' or a 'messages' list")
        if not any(s.role == Role.ASSISTANT for s in traj.steps):
            raise RunError(f"transcript {tid} has no assistant turn to grade")
        out.append((tid, traj))
    ids = [t for t, _ in out]
    if len(set(ids)) != len(ids):
        raise RunError("transcript ids must be unique")
    return out


def windows(traj: Trajectory) -> list[Trajectory]:
    """Split a transcript too long for the judge's evidence window into non-overlapping windows, each
    keeping the system prompt and first user turn."""
    if len(_fence_untrusted(traj)) <= DEFAULT_EVIDENCE_CHARS:
        return [traj]
    head = [s for s in traj.steps[:2] if s.role in (Role.SYSTEM, Role.USER)]
    rest = traj.steps[len(head):]
    head_len = len(_fence_untrusted(Trajectory(steps=head)))
    out, cur = [], []
    for s in rest:
        cur.append(s)
        if head_len + len(_fence_untrusted(Trajectory(steps=cur))) > WINDOW_CHARS and len(cur) > 1:
            out.append(Trajectory(steps=head + cur[:-1]))
            cur = [s]
    if cur:
        out.append(Trajectory(steps=head + cur))
    return [w for w in out if any(s.role == Role.ASSISTANT for s in w.steps)] or [traj]


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
    from fusion_first.goldset import load_gold
    from fusion_first.judge.judge import JUDGE_PROMPT_VERSION, judge_prompt_version
    from fusion_first.stats.calibration import run_calibration

    unknown = [c for c in checks if c not in REGISTRY]
    if unknown:
        raise RunError(f"unknown checks: {unknown}")
    manifest = json.dumps([{"id": t, "steps": len(tr.steps),
                            "sha256": hashlib.sha256(tr.model_dump_json().encode()).hexdigest()}
                           for t, tr in transcripts], sort_keys=True)
    # prompt.txt carries the manifest (ids + content hashes), so the run's commitment binds the logs.
    rd = new_run(workspace, f"logs:{manifest}", checks=list(checks), target="ollama:logs",
                 target_model="logs", grader=grader, calibration=calibration, run_id=run_id)
    rd.write_json(rd.root / "transcripts.json", [{"id": t, **tr.model_dump(mode="json")} for t, tr in transcripts])
    collector = CollectingJudgeClient()
    items: dict[str, list[dict]] = {}
    with judge_prompt_version(JUDGE_PROMPT_VERSION):
        for tid, traj in transcripts:
            parts = windows(traj)
            for check in checks:
                for w, part in enumerate(parts):
                    req = Judge(None)._build_request(part, get_rubric(check))
                    collector.requests[req.cache_key()] = req
                    items.setdefault(req.cache_key(), []).append(
                        {"transcript": tid, "check": check, "window": w, "windows": len(parts)})
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
    n_windowed = sum(1 for _, tr in transcripts if len(windows(tr)) > 1)
    rd.update_state(phase="awaiting_grades", n_tasks=len(tasks), n_graded=0,
                    message=f"{len(tasks)} questions to grade ({len(transcripts)} transcripts x {len(checks)} "
                            f"checks{f'; {n_windowed} long transcripts split into windows' if n_windowed else ''})")
    return rd


def is_log_run(rd: RunDir) -> bool:
    return (rd.root / "items.json").exists() and (rd.root / "transcripts.json").exists()


async def finalize_logs(rd: RunDir, *, allow_partial: bool = False, write: bool = True) -> dict:
    """Issue rate per check, flagged transcripts, grader accuracy; attack-run gates plus a minimum sample."""
    from fusion_first.judge.judge import judge_prompt_version

    snap = _snapshot(rd)
    with judge_prompt_version(snap.plan.judge_prompt_version):
        return await _finalize_logs(rd, snap, allow_partial, write)


def _item_list(raw) -> list[dict]:
    return raw if isinstance(raw, list) else [raw]  # runs created before multi-transcript keys


def _log_agreement(rd: RunDir, snap, check: str, items: dict):
    """The oracle cross-check on logs: canary tokens from each log's own system prompt."""
    from fusion_first.runs.oracle_check import Agreement, clear_cut_label, verdict_for

    trajs = {t["id"]: Trajectory.model_validate({"steps": t["steps"]})
             for t in rd.read_json(rd.root / "transcripts.json")}
    rubric = get_rubric(check)
    agg = Agreement(check)
    for key, metas in items.items():
        for meta in _item_list(metas):
            if meta["check"] != check or meta.get("windows", 1) != 1:
                continue
            traj = trajs.get(meta["transcript"])
            if traj is None:
                continue
            label = clear_cut_label(check, None, traj, traj.system_prompt())
            if label is None:
                continue
            verdict = verdict_for(snap.judge, key, rubric)
            if verdict is None:
                agg.unanswered += 1
                continue
            agg.add(label, verdict, {"transcript": meta["transcript"]})
    return agg


async def _finalize_logs(rd: RunDir, snap, allow_partial: bool, write: bool) -> dict:
    from fusion_first.engine.report import grade_for_rate
    from fusion_first.engine.user_scan import _worst_grade
    from fusion_first.runs.oracle_check import gate_reason
    from fusion_first.stats.calibration import run_calibration
    from fusion_first.stats.gate import load_policy
    from fusion_first.stats.metrics import wilson_interval

    graded = [t for t in rd.tasks() if t.key in snap.judge.entries]
    if len(graded) < snap.n_tasks and not allow_partial:
        raise RunError(f"{snap.n_tasks - len(graded)} questions are still ungraded")
    _validate_recorded_answers(rd, snap)
    items = rd.read_json(rd.root / "items.json")
    plan = snap.plan
    checks_out = {}
    for check in plan.checks:
        rubric = get_rubric(check)
        # per transcript: None = some window ungraded, else flagged if ANY window is flagged
        state: dict[str, dict] = {}
        for key, metas in items.items():
            for meta in _item_list(metas):
                if meta["check"] != check:
                    continue
                s = state.setdefault(meta["transcript"], {"ungraded": False, "flags": [], "windows": meta.get("windows", 1)})
                entry = snap.judge.entries.get(key)
                if entry is None:
                    s["ungraded"] = True
                    continue
                try:
                    v = Judge._parse(str(entry["text"]), rubric, str(entry.get("model", "")))
                except JudgeParseError:
                    s["ungraded"] = True
                    continue
                if v.is_issue:
                    s["flags"].append(v)
        flagged, n, ungraded = [], 0, 0
        for tid, s in state.items():
            if s["ungraded"] and not s["flags"]:
                ungraded += 1
                continue
            n += 1
            if s["flags"]:
                v = s["flags"][0]
                flagged.append({"transcript": tid, "criteria": sorted({c.id for f in s["flags"] for c in f.criteria if c.violated}),
                                "evidence": [c.evidence for c in v.criteria if c.violated][:3],
                                "rationale": v.rationale[:300]})
        rate = wilson_interval(len(flagged), n)
        reasons = []
        if ungraded:
            reasons.append(f"{ungraded} transcript(s) were never fully graded")
        if n < MIN_TRANSCRIPTS_FOR_GRADE:
            reasons.append(f"only {n} graded transcript(s); a grade needs at least {MIN_TRANSCRIPTS_FOR_GRADE} "
                           "(the rate and its interval are still shown)")
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
        agreement = _log_agreement(rd, snap, check, items) if rubric.kind == "safety" else None
        oracle_reason = gate_reason(agreement)
        if oracle_reason:
            reasons.append(oracle_reason)
        grade = "?" if reasons else grade_for_rate(len(flagged) / n)
        windowed = sum(1 for s in state.values() if s["windows"] > 1)
        checks_out[check] = {
            "kind": rubric.kind, "n_transcripts": n, "flagged": len(flagged), "windowed_transcripts": windowed,
            "issue_rate": {"point": round(rate.point, 4), "ci95": [round(rate.low, 4), round(rate.high, 4)]},
            "grade": grade, "grade_withheld": ("Grade withheld: " + "; ".join(reasons) + ".") if reasons else None,
            "grade_scale": "the attack-run issue-rate thresholds, applied to the observed transcripts",
            "grader_accuracy": ({"accuracy": round(acc.accuracy.point, 3),
                                 "ci95": [round(acc.accuracy.low, 3), round(acc.accuracy.high, 3)],
                                 "n": acc.n, "f1": round(acc.f1, 3)} if acc else None),
            "oracle_agreement": agreement.as_dict() if agreement else None,
            "flagged_transcripts": flagged[:50],
        }
    overall = _worst_grade([c["grade"] for c in checks_out.values()])
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
