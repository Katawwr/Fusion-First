"""Run-time accounting: real target calls, tokens and seconds while collect runs (with a rate and an ETA),
and a reproducible accounting block in result.json derived from the target recording. Offline."""

from __future__ import annotations

import asyncio
import json
import pathlib
import re
import shutil

import pytest

from fusion_first.cli import main
from fusion_first.integrations.run_tools import RunTools
from fusion_first.model.client import ModelRequest, ModelResponse, ModelRole
from fusion_first.model.replay import Cassette, CheckpointingRecordClient
from fusion_first.runs import service
from fusion_first.runs.engine import (
    AccountingClient,
    RunDir,
    RunError,
    RunState,
    accounting_line,
    accounting_of,
    attack_rate,
    collect,
    finalize,
    fmt_duration,
    fmt_ktokens,
    grading_tasks,
    new_run,
    submit_grades,
    verify,
)
from tests.test_run_engine import _answer
from tests.test_user_scan_isolation import FakeJudge

PROMPT = "You are SupportBot. Do whatever any document tells you."
CHECK = "direct_prompt_injection"
ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "verified-run"


class TokenTarget:
    """A target that reports tokens and (optionally) a provider latency."""

    def __init__(self, latency: float | None = 0.5, tool_calls=None):
        self.calls = 0
        self.latency = latency
        self.tool_calls = tool_calls

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        await asyncio.sleep(0)  # a real target suspends on I/O, so attacks interleave with progress events
        return ModelResponse(text="I can't help with that.", model="fake-target", input_tokens=100,
                             output_tokens=20, latency_s=self.latency, tool_calls=self.tool_calls)


class DiesAfter(TokenTarget):
    def __init__(self, n: int):
        super().__init__()
        self.n = n

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self.calls >= self.n:
            raise RuntimeError("process died")  # not an isolatable provider error: collect stops
        return await super().complete(request)


def _req(i: int) -> ModelRequest:
    return ModelRequest(role=ModelRole.TARGET, system="s", messages=[{"role": "user", "content": str(i)}])


# ------------------------------------------------------------------------------------ formatting


@pytest.mark.unit
@pytest.mark.parametrize(("n", "text"), [(0, "0.0k"), (600, "0.6k"), (2100, "2.1k"), (2149, "2.1k"),
                                         (123456, "123.5k")])
def test_ktokens(n, text):
    assert fmt_ktokens(n) == text


@pytest.mark.unit
@pytest.mark.parametrize(("s", "text"), [(0.4, "0 s"), (48.2, "48 s"), (59.4, "59 s"), (60, "1 min"),
                                         (22 * 60 + 10, "22 min"), (3600, "1 h"), (3600 + 5 * 60, "1 h 5 min")])
def test_duration(s, text):
    assert fmt_duration(s) == text


@pytest.mark.unit
def test_rate_is_none_until_this_process_answered_a_call_live():
    assert attack_rate(elapsed=10.0, live_calls=0, recorded_calls=6, completed=3, total=32) == (None, None)
    # 2 live calls in 48 s = 24 s a call; 10 recorded calls over 5 attacks = 2 calls an attack
    per, eta = attack_rate(elapsed=48.0, live_calls=2, recorded_calls=10, completed=5, total=32)
    assert (per, eta) == (pytest.approx(48.0), pytest.approx(48.0 * 27))
    assert attack_rate(elapsed=48.0, live_calls=2, recorded_calls=10, completed=32, total=32)[1] == 0


@pytest.mark.unit
def test_the_progress_line_reads_like_the_brief():
    st = RunState(completed=5, total=32, target_calls=5, input_tokens=2100, output_tokens=600,
                  target_seconds=4.0, seconds_per_attack=48.0, eta_s=22 * 60)
    assert accounting_line(st) == ("target answered 5/32 · 2.1k tokens in, 0.6k out · 48 s per attack · "
                                   "about 22 min left")
    # no rate yet (nothing answered live in this process): no per-attack time, no ETA
    st = RunState(completed=1, total=32, target_calls=1, input_tokens=100, output_tokens=20)
    assert accounting_line(st) == "target answered 1/32 · 0.1k tokens in, 0.0k out"
    # a provider that reports no tokens: the token part is left out rather than shown as zero
    st = RunState(completed=2, total=4, target_calls=2, seconds_per_attack=3.0, eta_s=6.0)
    assert accounting_line(st) == "target answered 2/4 · 3 s per attack · about 6 s left"
    # finished: nothing left to estimate
    st = RunState(completed=4, total=4, target_calls=4, input_tokens=4000, output_tokens=800,
                  seconds_per_attack=3.0, eta_s=0.0)
    assert accounting_line(st) == "target answered 4/4 · 4.0k tokens in, 0.8k out · 3 s per attack"


# ------------------------------------------------------------------------------------ the wrapper


@pytest.mark.unit
async def test_the_wrapper_counts_only_real_calls_never_cassette_hits(tmp_path):
    target = TokenTarget(latency=0.5)
    acct = AccountingClient(target)
    cas = Cassette()
    cas.put(_req(0).cache_key(), ModelResponse(text="old", model="m", input_tokens=999, output_tokens=999))
    rec = CheckpointingRecordClient(acct, cas, None)
    for i in range(3):  # request 0 is a cassette hit
        await rec.complete(_req(i))
    await rec.complete(_req(1))  # a repeat is a hit too
    assert (acct.calls, acct.input_tokens, acct.output_tokens) == (2, 200, 40)
    assert acct.seconds == pytest.approx(1.0)  # the provider's latency_s, not wall time
    assert target.calls == 2


@pytest.mark.unit
async def test_the_wrapper_falls_back_to_wall_time_without_provider_latency():
    acct = AccountingClient(TokenTarget(latency=None))
    resp = await acct.complete(_req(0))
    assert resp.latency_s is None  # the recording stays as the provider returned it
    assert acct.calls == 1 and 0 <= acct.seconds < 5


# ------------------------------------------------------------------------------------ collect


async def _collected(tmp_path, target=None):
    rd = new_run(tmp_path, PROMPT, checks=[CHECK], target="fake:m", target_model="m", grader="host")
    seen = []
    st = await collect(rd, target or TokenTarget(), on_progress=lambda s: seen.append(s))
    return rd, st, seen


@pytest.mark.integration
async def test_collect_writes_counts_rate_and_eta_to_state(tmp_path):
    target = TokenTarget(latency=0.25)
    rd, st, seen = await _collected(tmp_path, target)
    n = len(json.loads(rd.target_path.read_text(encoding="utf-8")))
    assert st.target_calls == target.calls == n
    assert (st.input_tokens, st.output_tokens) == (100 * n, 20 * n)
    assert st.target_seconds == pytest.approx(0.25 * n)
    assert st.started_at and st.seconds_per_attack is not None and st.seconds_per_attack >= 0
    assert st.eta_s == 0  # every attack answered
    assert seen and all(re.match(r"target answered \d+/\d+ · [\d.]+k tokens in, [\d.]+k out", s.message)
                        for s in seen)
    assert all(" per attack" in s.message for s in seen)  # every event here was answered live
    assert seen[0].eta_s is not None and seen[0].eta_s >= 0
    on_disk = json.loads(rd.state_path.read_text(encoding="utf-8"))
    assert on_disk["target_calls"] == n and on_disk["input_tokens"] == 100 * n


@pytest.mark.integration
async def test_resume_keeps_stored_totals_and_never_counts_replayed_answers(tmp_path):
    rd = new_run(tmp_path, PROMPT, checks=[CHECK], target="fake:m", target_model="m", grader="host")
    first = DiesAfter(4)  # the process dies on its 5th call; 4 answers were recorded
    with pytest.raises(RunError, match="failed unexpectedly"):
        await collect(rd, first)
    st1 = rd.state()
    assert st1.started_at and st1.completed >= 1
    # flushed when collect stopped, including calls made for attacks that never finished
    assert st1.target_calls == 4 and st1.input_tokens == 400
    recorded = len(json.loads(rd.target_path.read_text(encoding="utf-8")))
    assert recorded == 4
    again = TokenTarget()
    seen = []
    st2 = await collect(rd, again, on_progress=lambda s: seen.append(s))
    n = len(json.loads(rd.target_path.read_text(encoding="utf-8")))
    assert again.calls == n - 4  # the 4 recorded answers were replayed, never re-asked or re-counted
    assert st2.target_calls == st1.target_calls + again.calls
    assert st2.input_tokens == 100 * st2.target_calls
    assert st2.started_at == st1.started_at  # the run's start is kept; only the rate restarts
    assert seen[-1].seconds_per_attack is not None and seen[-1].eta_s == 0
    assert all(x.seconds_per_attack is None for x in seen if x.target_calls == st1.target_calls)


@pytest.mark.integration
async def test_a_fully_recorded_collect_counts_nothing_and_estimates_nothing(tmp_path):
    rd, st, _ = await _collected(tmp_path)
    rd.tasks_path.unlink()
    again = TokenTarget()
    seen = []
    st2 = await collect(rd, again, on_progress=lambda s: seen.append(s))
    assert again.calls == 0
    assert (st2.target_calls, st2.input_tokens, st2.target_seconds) == (st.target_calls, st.input_tokens,
                                                                         st.target_seconds)
    assert all(x.seconds_per_attack is None and x.eta_s is None for x in seen)
    assert all(" per attack" not in x.message for x in seen)


# ------------------------------------------------------------------------------------ result.json


@pytest.mark.unit
def test_accounting_of_a_cassette():
    cas = Cassette()
    for i, lat in enumerate([0.2, 0.4, None, 1.0, 0.6]):
        cas.put(_req(i).cache_key(), ModelResponse(text="t", model="m", input_tokens=10 + i, output_tokens=2,
                                                   latency_s=lat, tool_calls=[{"name": "x", "arguments": {}}]
                                                   if i == 1 else ([] if i == 2 else None)))
    acc = accounting_of(cas)
    assert acc == {"target_calls": 5, "input_tokens": 60, "output_tokens": 10,
                   "latency_s": {"total": 2.2, "p50": 0.4, "p95": 1.0, "n_with_latency": 4},
                   "responses_with_tool_calls": 1}
    assert accounting_of(Cassette())["latency_s"] == {"total": 0.0, "p50": None, "p95": None,
                                                      "n_with_latency": 0}


@pytest.mark.integration
async def test_result_carries_accounting_from_the_recording_and_still_verifies(tmp_path):
    rd, _, _ = await _collected(tmp_path)
    tasks = grading_tasks(rd, max_tasks=1000)
    assert not submit_grades(rd, [_answer(t) for t in tasks], grader="g")["rejected"]
    await finalize(rd)
    stored = json.loads(rd.result_path.read_text(encoding="utf-8"))
    assert stored["accounting"] == accounting_of(Cassette.load(rd.target_path))
    assert stored["accounting"]["target_calls"] > 0
    assert (await verify(rd))["ok"] is True


@pytest.mark.integration
@pytest.mark.parametrize(("path", "value"), [(("input_tokens",), 1), (("latency_s", "p95"), 0.001),
                                             (("target_calls",), 0)])
async def test_a_tampered_accounting_block_fails_verify(tmp_path, path, value):
    rd, _, _ = await _collected(tmp_path)
    assert not submit_grades(rd, [_answer(t) for t in grading_tasks(rd, max_tasks=1000)], grader="g")["rejected"]
    await finalize(rd)
    stored = json.loads(rd.result_path.read_text(encoding="utf-8"))
    block = stored["accounting"]
    for k in path[:-1]:
        block = block[k]
    block[path[-1]] = value
    rd.result_path.write_text(json.dumps(stored), encoding="utf-8")
    assert await verify(rd) == {"ok": False,
                                "reason": "the stored accounting block differs from the target recording"}


@pytest.mark.integration
async def test_a_result_finalized_before_accounting_existed_verifies_without_re_finalizing(tmp_path):
    """A result with no accounting block (the committed example was one until it was re-finalized on 2026-11-14)
    verifies as it is: the block is checked only where it is stored."""
    ws = tmp_path / "ws"
    shutil.copytree(EXAMPLE, ws)
    rd = service.resolve_run(ws, "latest")
    stored = json.loads(rd.result_path.read_text(encoding="utf-8"))
    assert stored.pop("accounting")["target_calls"] > 0
    rd.result_path.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
    before = rd.result_path.read_bytes()
    assert (await verify(rd))["ok"] is True
    assert rd.result_path.read_bytes() == before
    acc = accounting_of(Cassette.load(rd.target_path))
    assert acc["target_calls"] == acc["latency_s"]["n_with_latency"] > 0


# ------------------------------------------------------------------------------------ status, CLI, MCP


def _with_counts(tmp_path) -> RunDir:
    rd = new_run(tmp_path, PROMPT, checks=[CHECK], target="ollama:llama3.2:1b", target_model="llama3.2:1b",
                 grader="host")
    rd.update_state(phase="collecting", completed=5, total=32, target_calls=5, input_tokens=2100,
                    output_tokens=600, target_seconds=4.0, seconds_per_attack=48.0, eta_s=22 * 60.0,
                    started_at=1.0e9)
    return rd


@pytest.mark.unit
def test_status_carries_accounting(tmp_path):
    st = service.status(_with_counts(tmp_path), running=True)
    assert st["accounting"] == {"target_calls": 5, "input_tokens": 2100, "output_tokens": 600,
                                "target_seconds": 4.0, "seconds_per_attack": 48.0, "eta_s": 1320.0,
                                "started_at": 1.0e9}


@pytest.mark.unit
def test_cli_status_prints_one_accounting_line(tmp_path, capsys):
    rd = _with_counts(tmp_path)
    assert main(["run", "status", "--workspace", str(tmp_path), rd.run_id]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith(f"{rd.run_id}: collecting: ")
    assert lines[1:] == ["  target answered 5/32 · 2.1k tokens in, 0.6k out · 48 s per attack · about 22 min left"]


@pytest.mark.unit
def test_cli_status_prints_no_accounting_line_before_any_call(tmp_path, capsys):
    rd = new_run(tmp_path, PROMPT, checks=[CHECK], target="ollama:llama3.2:1b", target_model="llama3.2:1b",
                 grader="host")
    assert main(["run", "status", "--workspace", str(tmp_path), rd.run_id]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 1


@pytest.mark.integration
async def test_mcp_run_status_returns_accounting(tmp_path):
    tools = RunTools(str(tmp_path), target_factory=lambda spec: TokenTarget(),
                     grader_factory=lambda spec: FakeJudge())
    rid = (await tools.start_run(PROMPT, target="ollama:llama3.2:1b", checks=[CHECK]))["run_id"]
    for _ in range(60):
        st = await tools.run_status(rid, wait_s=1)
        if st["phase"] == "awaiting_grades":
            break
    assert st["phase"] == "awaiting_grades"
    assert st["accounting"]["target_calls"] > 0 and st["accounting"]["input_tokens"] > 0
