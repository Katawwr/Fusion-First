"""The context-handoff hook (scripts/hooks/context_handoff.py): at 85% of the context window it tells
Claude to write HANDOFF.md, commit, and start the continuation session. Offline; synthetic transcripts."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = runpy.run_path(str(ROOT / "scripts/hooks/context_handoff.py"), run_name="context_handoff")
handle, context_tokens = HOOK["handle"], HOOK["context_tokens"]
ENV = {"CONTEXT_HANDOFF_WINDOW": "1000000"}


def _assistant(total: int, sidechain: bool = False) -> dict:
    return {"type": "assistant", "isSidechain": sidechain, "message": {"usage": {
        "input_tokens": 2, "cache_creation_input_tokens": 8, "cache_read_input_tokens": total - 110,
        "output_tokens": 100}}}


def _transcript(tmp_path: Path, *records: dict) -> Path:
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return p


def _payload(path: Path, event: str = "PostToolUse", session: str = "s1", **extra) -> dict:
    return {"hook_event_name": event, "session_id": session, "transcript_path": str(path), **extra}


@pytest.mark.unit
def test_the_context_is_the_last_main_thread_request_plus_its_output(tmp_path):
    t = _transcript(tmp_path, _assistant(500_000), {"type": "user"}, _assistant(900_000, sidechain=True))
    assert context_tokens(t) == 500_000


@pytest.mark.unit
def test_after_a_compaction_the_old_size_does_not_count(tmp_path):
    t = _transcript(tmp_path, _assistant(960_000), {"type": "system", "subtype": "compact_boundary"})
    assert context_tokens(t) is None


@pytest.mark.unit
def test_below_the_threshold_nothing_happens(tmp_path):
    t = _transcript(tmp_path, _assistant(849_000))
    assert handle(_payload(t), ENV, tmp_path / "state") is None


@pytest.mark.unit
def test_at_85_percent_it_asks_for_the_handoff_once(tmp_path):
    t = _transcript(tmp_path, _assistant(860_000))
    out = handle(_payload(t), ENV, tmp_path / "state")
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "86%" in ctx and "HANDOFF.md" in ctx and "fusion-continue-a" in ctx and "fusion-continue-b" in ctx
    assert handle(_payload(t), ENV, tmp_path / "state") is None  # once per session
    other = handle(_payload(t, session="s2"), ENV, tmp_path / "state")
    assert other is not None  # state is per session


@pytest.mark.unit
def test_near_auto_compaction_it_reminds_once(tmp_path):
    state = tmp_path / "state"
    handle(_payload(_transcript(tmp_path, _assistant(860_000))), ENV, state)
    out = handle(_payload(_transcript(tmp_path, _assistant(935_000))), ENV, state)
    assert "reminder" in out["hookSpecificOutput"]["additionalContext"]
    assert handle(_payload(_transcript(tmp_path, _assistant(940_000))), ENV, state) is None


@pytest.mark.unit
def test_at_stop_it_keeps_the_turn_going_unless_a_stop_hook_already_did(tmp_path):
    t = _transcript(tmp_path, _assistant(870_000))
    assert handle(_payload(t, "Stop", stop_hook_active=True), ENV, tmp_path / "state") is None
    out = handle(_payload(t, "Stop"), ENV, tmp_path / "state")
    assert out["decision"] == "block" and "HANDOFF.md" in out["reason"]


@pytest.mark.unit
def test_a_user_prompt_gets_the_notice_as_context(tmp_path):
    out = handle(_payload(_transcript(tmp_path, _assistant(870_000)), "UserPromptSubmit"), ENV, tmp_path / "state")
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"


@pytest.mark.unit
@pytest.mark.parametrize("env,payload", [
    ({**ENV, "CONTEXT_HANDOFF_OFF": "1"}, None),
    (ENV, {"hook_event_name": "PostToolUse", "session_id": "s", "transcript_path": "/no/such/file.jsonl"}),
    (ENV, {"hook_event_name": "PostToolUse"}),
    (ENV, "not a dict"),
])
def test_it_never_fails_and_stays_silent_when_it_cannot_tell(tmp_path, env, payload):
    p = payload or _payload(_transcript(tmp_path, _assistant(990_000)))
    assert handle(p, env, tmp_path / "state") is None


@pytest.mark.unit
def test_the_threshold_and_window_are_configurable_and_a_bad_value_falls_back(tmp_path):
    t = _transcript(tmp_path, _assistant(150_000))
    assert handle(_payload(t), {"CONTEXT_HANDOFF_WINDOW": "200000", "CONTEXT_HANDOFF_PCT": "70"},
                  tmp_path / "state") is not None
    big = _transcript(tmp_path, _assistant(990_000))
    assert handle(_payload(big), {"CONTEXT_HANDOFF_WINDOW": "lots"}, tmp_path / "state2") is not None


@pytest.mark.unit
def test_the_script_reads_stdin_and_always_exits_zero(tmp_path):
    import subprocess
    import sys
    t = _transcript(tmp_path, _assistant(870_000))
    env = {"CONTEXT_HANDOFF_STATE_DIR": str(tmp_path / "st"), "PATH": "", "SYSTEMROOT": "C:\\Windows"}
    run = lambda stdin: subprocess.run([sys.executable, str(ROOT / "scripts/hooks/context_handoff.py")],  # noqa: E731
                                       input=stdin, capture_output=True, text=True, env=env, timeout=30)
    ok = run(json.dumps(_payload(t)))
    assert ok.returncode == 0 and "HANDOFF.md" in json.loads(ok.stdout)["hookSpecificOutput"]["additionalContext"]
    bad = run("{not json")
    assert bad.returncode == 0 and bad.stdout == ""
