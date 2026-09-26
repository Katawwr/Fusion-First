"""The keyless run engine: COLLECT -> GRADE -> FINALIZE, so any grader can judge without an API key.

Why three phases: the judge is the only step that needs a strong model, and in agentic workflows the
strongest model available is often the HOST agent itself (e.g. a Claude Code subagent), which an MCP
server cannot call (MCP sampling is unsupported in Claude Code and deprecated in the spec). So:

  1. collect  — run the real scan against the real target (local Ollama or the claude CLI), record
                every target response, and capture every question the judge would be asked — plus
                the blind gold-set questions for the same checks (in-run calibration). The judge
                calls are answered by a stand-in that records them; verdicts don't steer the scan.
  2. grade    — answer those questions by ANY grader: a built-in backend (claude CLI subscription,
                local probability judge) or an external one (the host agent via MCP, a human, a
                script). Answers are validated by the production parser, evidence must be quoted
                from the transcript, and each task can be answered once.
  3. finalize — replay the unchanged scan pipeline from the two recordings. The card's Bar A is the
                in-run accuracy of THIS grader on the blind gold questions it answered unknowingly.

Everything lives in `<workspace>/.fusion/runs/<run_id>/`, which is the proof artifact: `verify`
re-derives the result offline from it and fails on any drift.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from fusion.errors import FusionProviderError, IsolatableError, JudgeUndecided
from fusion.judge.judge import Judge, JudgeParseError, build_system_prompt
from fusion.judge.rubric import REGISTRY, get_rubric
from fusion.model.client import ModelClient, ModelRequest, ModelResponse
from fusion.model.replay import (
    Cassette,
    CassetteMiss,
    CheckpointingRecordClient,
    ReplayModelClient,
)
from fusion.schemas import ScanEventType, ScanResult, ScanTier

RUNS_DIRNAME = os.path.join(".fusion", "runs")


class RunError(RuntimeError):
    """A run cannot proceed (bad state, target failure, incomplete grading)."""


class TargetNotRecorded(FusionProviderError):
    """Finalize: this target response was never recorded (it failed in collect) — unscored."""


class NotGraded(JudgeUndecided):
    """Finalize with allow_partial: this judge question was never answered — unscored."""


# ------------------------------------------------------------------------------------ state


@dataclass
class RunPlan:
    run_id: str
    checks: list[str]
    tier: str
    target: str  # e.g. "ollama:llama3.2:1b" | "claude-cli:claude-haiku-4-5"
    target_model: str
    grader: str  # e.g. "host" | "claude_cli" | "ollama_prob:qwen2.5:7b"
    prompt_sha256: str
    calibration: bool = True
    version: str = "v1"


@dataclass
class Task:
    task_id: str
    check: str
    key: str  # the judge request cache key (internal; never sent to external graders)


@dataclass
class RunState:
    phase: str = "created"  # created | collecting | awaiting_grades | grading | done | failed
    completed: int = 0
    total: int = 0
    message: str = ""
    n_tasks: int = 0
    n_graded: int = 0
    rejected: list[dict] = field(default_factory=list)


class RunDir:
    def __init__(self, workspace: str | pathlib.Path, run_id: str):
        self.root = pathlib.Path(workspace) / RUNS_DIRNAME / run_id
        self.run_id = run_id

    # files
    plan_path = property(lambda self: self.root / "plan.json")
    prompt_path = property(lambda self: self.root / "prompt.txt")
    target_path = property(lambda self: self.root / "target.cassette.json")
    judge_path = property(lambda self: self.root / "judge.cassette.json")
    requests_path = property(lambda self: self.root / "judge.requests.json")
    tasks_path = property(lambda self: self.root / "tasks.json")
    state_path = property(lambda self: self.root / "state.json")
    result_path = property(lambda self: self.root / "result.json")
    report_path = property(lambda self: self.root / "report.html")
    secret_path = property(lambda self: self.root / ".secret")

    def _write(self, path: pathlib.Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    def write_json(self, path: pathlib.Path, obj) -> None:
        self._write(path, json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))

    def read_json(self, path: pathlib.Path):
        return json.loads(path.read_text(encoding="utf-8"))

    def plan(self) -> RunPlan:
        return RunPlan(**self.read_json(self.plan_path))

    def prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")

    def state(self) -> RunState:
        return RunState(**self.read_json(self.state_path)) if self.state_path.exists() else RunState()

    def save_state(self, st: RunState) -> None:
        self.write_json(self.state_path, asdict(st))

    def tasks(self) -> list[Task]:
        return [Task(**t) for t in self.read_json(self.tasks_path)] if self.tasks_path.exists() else []

    def requests(self) -> dict[str, dict]:
        return self.read_json(self.requests_path) if self.requests_path.exists() else {}


def new_run(
    workspace: str | pathlib.Path,
    system_prompt: str,
    *,
    checks: list[str],
    target: str,
    target_model: str,
    grader: str,
    tier: str = "quick",
    calibration: bool = True,
    run_id: str | None = None,
) -> RunDir:
    unknown = [c for c in checks if c not in REGISTRY]
    if unknown:
        raise RunError(f"unknown checks: {unknown}")
    rid = run_id or secrets.token_hex(6)
    rd = RunDir(workspace, rid)
    if rd.root.exists():
        raise RunError(f"run {rid} already exists")
    rd.root.mkdir(parents=True)
    rd._write(rd.prompt_path, system_prompt)
    rd._write(rd.secret_path, secrets.token_hex(16))
    plan = RunPlan(
        run_id=rid, checks=list(checks), tier=tier, target=target, target_model=target_model,
        grader=grader, prompt_sha256=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        calibration=calibration,
    )
    rd.write_json(rd.plan_path, asdict(plan))
    rd.save_state(RunState())
    return rd


# ------------------------------------------------------------------------------------ collect


class CollectingJudgeClient:
    """Stands in for the judge during collect: records every judge request and answers 'nothing
    violated' (a valid, parseable verdict). Scan control flow never depends on verdicts, so the
    target requests are identical to what a real judge would have caused."""

    def __init__(self):
        self.requests: dict[str, ModelRequest] = {}

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests[request.cache_key()] = request
        ids = request.response_schema["properties"]["criteria"]["items"]["properties"]["id"]["enum"]
        body = {"criteria": [{"id": i, "violated": False, "evidence": ""} for i in ids],
                "rationale": "collect", "confidence": 0.5}
        return ModelResponse(text=json.dumps(body), model="collector")


_CHECK_BY_PROMPT = {build_system_prompt(get_rubric(c)): c for c in REGISTRY}


def _check_of(req: ModelRequest) -> str:
    return _CHECK_BY_PROMPT.get(req.system, "unknown")


def _task_id(secret: str, key: str) -> str:
    return "t_" + hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()[:14]


async def collect(
    rd: RunDir,
    target_client: ModelClient,
    *,
    concurrency: int = 1,
    on_progress: Callable[[RunState], None] | None = None,
) -> RunState:
    """Phase 1. Runs the scan against the real target (recorded) and captures the judge questions."""
    from fusion.engine.user_scan import run_user_scan
    from fusion.stats.calibration import run_calibration

    plan = rd.plan()
    st = rd.state()
    st.phase = "collecting"
    rd.save_state(st)
    recorder = CheckpointingRecordClient(target_client, Cassette.load(rd.target_path), rd.target_path, every=1)
    collector = CollectingJudgeClient()
    try:
        async for ev in run_user_scan(
            system_prompt=rd.prompt(), checks=plan.checks, tier=ScanTier(plan.tier),
            demonstration=False, judge_client=collector, target_client=recorder,
            target_model_id=plan.target_model, judge_model="collector", concurrency=concurrency,
        ):
            if ev.type == ScanEventType.PROBE_RESULT:
                st.completed, st.total = ev.completed, ev.total
                st.message = f"target answered {ev.completed}/{ev.total}"
                rd.save_state(st)
                if on_progress:
                    on_progress(st)
            elif ev.type == ScanEventType.ERROR:
                st.phase, st.message = "failed", f"{ev.code}: {ev.message}"
                rd.save_state(st)
                raise RunError(st.message)
        if plan.calibration:
            from fusion.goldset import load_gold

            for check in plan.checks:
                if any(c.split == "blind" for c in load_gold(check, plan.version)):
                    await run_calibration(check, collector, version=plan.version, split="blind")
    finally:
        recorder.flush()

    secret = rd.secret_path.read_text(encoding="utf-8").strip()
    tasks = sorted(
        (Task(task_id=_task_id(secret, k), check=_check_of(r), key=k) for k, r in collector.requests.items()),
        key=lambda t: t.task_id,  # opaque, shuffled order: calibration items are indistinguishable
    )
    rd.write_json(rd.tasks_path, [asdict(t) for t in tasks])
    rd.write_json(rd.requests_path, {k: r.model_dump(mode="json") for k, r in collector.requests.items()})
    st = rd.state()
    st.phase, st.n_tasks, st.message = "awaiting_grades", len(tasks), f"{len(tasks)} questions to grade"
    rd.save_state(st)
    return st


# ------------------------------------------------------------------------------------ grade


def grading_tasks(rd: RunDir, max_tasks: int = 8) -> list[dict]:
    """The next ungraded questions, in the exact form the built-in judge would see them."""
    graded = Cassette.load(rd.judge_path).entries
    reqs = rd.requests()
    out = []
    for t in rd.tasks():
        if t.key in graded:
            continue
        r = reqs[t.key]
        out.append({
            "task_id": t.task_id,
            "check": t.check,
            "instructions": r["system"],
            "transcript": r["messages"][0]["content"],
            "answer_schema": r["response_schema"],
        })
        if len(out) >= max_tasks:
            break
    return out


def _norm(text: str) -> str:
    return " ".join(str(text).split()).casefold().strip(" \"'`.…")


def submit_grades(rd: RunDir, grades: list[dict], *, grader: str) -> dict:
    """Validate and store external answers. Each must parse under the production judge parser,
    quote evidence that appears in the transcript for every violated criterion, and target a task
    that isn't graded yet. Returns accepted/rejected/remaining."""
    by_id = {t.task_id: t for t in rd.tasks()}
    reqs = rd.requests()
    cas = Cassette.load(rd.judge_path)
    accepted, rejected = [], []
    for g in grades:
        tid = str(g.get("task_id", ""))
        task = by_id.get(tid)
        if task is None:
            rejected.append({"task_id": tid, "reason": "unknown task"})
            continue
        if task.key in cas.entries:
            rejected.append({"task_id": tid, "reason": "already graded"})
            continue
        answer = {k: g.get(k) for k in ("criteria", "rationale", "confidence")}
        text = json.dumps(answer, ensure_ascii=False)
        try:
            verdict = Judge._parse(text, get_rubric(task.check), grader)
        except JudgeParseError as e:
            rejected.append({"task_id": tid, "reason": f"invalid answer: {e}"})
            continue
        transcript = _norm(reqs[task.key]["messages"][0]["content"])
        ungrounded = [
            c.id for c in verdict.criteria
            if c.violated and (not _norm(c.evidence) or _norm(c.evidence) not in transcript)
        ]
        if ungrounded:
            rejected.append({"task_id": tid, "reason": f"evidence not quoted from the transcript: {ungrounded}"})
            continue
        cas.put(task.key, ModelResponse(text=text, model=f"host:{grader}"))
        accepted.append(tid)
    cas.save(rd.judge_path)
    st = rd.state()
    st.n_graded = sum(1 for t in by_id.values() if t.key in cas.entries)
    st.rejected = (st.rejected + rejected)[-50:]
    if st.n_graded >= st.n_tasks:
        st.phase, st.message = "ready", "all questions graded — call finalize"
    rd.save_state(st)
    return {"accepted": accepted, "rejected": rejected, "remaining": st.n_tasks - st.n_graded}


async def grade_with(rd: RunDir, judge_client: ModelClient, *, label: str, stop_on_error: bool = False) -> dict:
    """Answer every pending question with a built-in grader (claude CLI, local probability judge…).
    Isolatable failures stay pending (retry later); run-level failures (usage limit) propagate."""
    from fusion.errors import isolatable

    reqs = rd.requests()
    cas = Cassette.load(rd.judge_path)
    done = failed = 0
    for t in rd.tasks():
        if t.key in cas.entries:
            continue
        req = ModelRequest(**reqs[t.key])
        try:
            resp = await judge_client.complete(req)
        except Exception as exc:  # noqa: BLE001
            if not isolatable(exc) or stop_on_error:
                cas.save(rd.judge_path)
                raise
            failed += 1
            continue
        cas.put(t.key, resp.model_copy(update={"model": f"{label}:{resp.model}"}))
        done += 1
        if done % 5 == 0:
            cas.save(rd.judge_path)
    cas.save(rd.judge_path)
    st = rd.state()
    st.n_graded = sum(1 for t in rd.tasks() if t.key in cas.entries)
    if st.n_graded >= st.n_tasks:
        st.phase, st.message = "ready", "all questions graded — call finalize"
    rd.save_state(st)
    return {"graded": done, "failed": failed, "remaining": st.n_tasks - st.n_graded}


# ------------------------------------------------------------------------------------ finalize


class _TargetReplay:
    def __init__(self, cas: Cassette):
        self._inner = ReplayModelClient(cas, strict=True)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            return await self._inner.complete(request)
        except CassetteMiss as e:
            raise TargetNotRecorded("this target response was not recorded (it failed in collect)") from e


class _JudgeReplay:
    def __init__(self, cas: Cassette, allow_partial: bool):
        self._inner = ReplayModelClient(cas, strict=True)
        self._partial = allow_partial

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            return await self._inner.complete(request)
        except CassetteMiss:
            if self._partial:
                raise NotGraded("this question was never graded") from None
            raise


def _in_run_accuracy(judge_client, plan: RunPlan, grader_label: str):
    from fusion.stats.calibration import run_calibration

    async def provider(check: str, judge_id: str):
        if not plan.calibration:
            return None, "", "In-run calibration was switched off for this run.", ""
        try:
            outcome = await run_calibration(check, judge_client, version=plan.version, split="blind")
        except (ValueError, IsolatableError, CassetteMiss) as e:
            return None, "", f"The grader's accuracy could not be measured in this run ({e}).", ""
        return (outcome.result, outcome.gold_version, "",
                f"measured in this run on {outcome.result.n} blind known-answer cases")

    return provider


async def finalize(rd: RunDir, *, allow_partial: bool = False, write: bool = True) -> ScanResult:
    """Phase 3. Replays the scan from the recordings; writes result.json and report.html
    (`write=False` re-derives without touching the run directory — used by verify)."""
    from fusion.engine.report_html import render_dashboard_html
    from fusion.engine.user_scan import ErrorBreaker, run_user_scan
    from fusion.model.registry import JudgeChoice

    plan = rd.plan()
    st = rd.state()
    if st.n_graded < st.n_tasks and not allow_partial:
        raise RunError(f"{st.n_tasks - st.n_graded} questions are still ungraded")
    judge_cas = Cassette.load(rd.judge_path)
    judge_client = _JudgeReplay(judge_cas, allow_partial)
    grader_label = plan.grader
    choice = JudgeChoice(
        grader_label,
        "host_unverified" if plan.grader == "host" else "declared",
        "The grader's identity is not verified by Fusion; its accuracy is MEASURED in this run on "
        "blind known-answer cases it could not tell apart from the real questions.",
    )
    result: ScanResult | None = None
    async for ev in run_user_scan(
        system_prompt=rd.prompt(), checks=plan.checks, tier=ScanTier(plan.tier), demonstration=False,
        judge_client=judge_client, target_client=_TargetReplay(Cassette.load(rd.target_path)),
        target_model_id=plan.target_model, judge_model=grader_label, concurrency=1,
        judge_choice=choice, judge_backend="host" if plan.grader == "host" else plan.grader,
        judge_accuracy_provider=_in_run_accuracy(judge_client, plan, grader_label),
        # Replay: a missing answer is "not graded", never a backend outage — no circuit breaker.
        breaker=ErrorBreaker(max_consecutive=10**9, max_error_rate=2.0, min_seen=10**9),
    ):
        if ev.type == ScanEventType.SCAN_COMPLETED:
            result = ev.result
        elif ev.type == ScanEventType.ERROR:
            raise RunError(f"{ev.code}: {ev.message}")
    if result is None:
        raise RunError("the replayed scan produced no result")
    if write:
        rd.write_json(rd.result_path, {**result.model_dump(mode="json"), "run": asdict(plan),
                                       "commitment": commitment(rd)})
        rd._write(rd.report_path, render_dashboard_html(result.cards, f"Fusion run {plan.run_id}"))
        st.phase, st.message = "done", f"overall grade {result.overall_grade}"
        rd.save_state(st)
    return result


def commitment(rd: RunDir) -> str:
    """Hash over everything the result is derived from (plan, prompt, both recordings)."""
    h = hashlib.sha256()
    for p in (rd.plan_path, rd.prompt_path, rd.target_path, rd.judge_path):
        h.update(p.name.encode())
        h.update(p.read_bytes() if p.exists() else b"")
    return h.hexdigest()


async def verify(rd: RunDir) -> dict:
    """Re-derive the result offline from the run directory and compare with the stored one."""
    stored = rd.read_json(rd.result_path)
    if stored.get("commitment") != commitment(rd):
        return {"ok": False, "reason": "inputs changed since the result was produced (commitment mismatch)"}
    fresh = await finalize(rd, allow_partial=True, write=False)
    ok = fresh.model_dump(mode="json")["cards"] == stored["cards"]
    return {"ok": ok, "reason": "" if ok else "re-derived cards differ from the stored result"}
