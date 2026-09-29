"""Context handoff hook: at 85% of the context window, have Claude write HANDOFF.md, commit it, and start
a fresh session that continues from it (policy: CLAUDE.md, "Context handoff").

Registered on PostToolUse (catches long autonomous turns), Stop and UserPromptSubmit. The context size
is the last main-thread request in the session transcript: input + cache write + cache read tokens,
plus that reply's output. Fires once per session at the threshold and once more near auto-compaction.
Never raises and always exits 0, so it cannot trap a session; when it cannot tell, it stays silent.

Environment: CONTEXT_HANDOFF_WINDOW (tokens, default 1000000), CONTEXT_HANDOFF_PCT (85),
CONTEXT_HANDOFF_REMIND_PCT (93), CONTEXT_HANDOFF_OFF=1 to disable, CONTEXT_HANDOFF_STATE_DIR.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

DEFAULTS = {"CONTEXT_HANDOFF_WINDOW": 1_000_000, "CONTEXT_HANDOFF_PCT": 85, "CONTEXT_HANDOFF_REMIND_PCT": 93}
ROUTINES = ("fusion-continue-a", "fusion-continue-b")
_USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def context_tokens(transcript: Path) -> int | None:
    """Tokens the next request carries, from the newest main-thread usage record; None if unknown or
    if the context was compacted after it."""
    size = transcript.stat().st_size
    for chunk in (1 << 20, 16 << 20):
        with transcript.open("rb") as f:
            f.seek(max(0, size - chunk))
            lines = f.read().splitlines()
        for raw in reversed(lines):
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
                return None
            usage = (rec.get("message") or {}).get("usage") if rec.get("type") == "assistant" else None
            if isinstance(usage, dict) and not rec.get("isSidechain"):
                return sum(int(usage.get(k) or 0) for k in _USAGE_KEYS)
        if chunk >= size:
            break
    return None


def _number(env: dict, key: str) -> float:
    try:
        return float(env.get(key, DEFAULTS[key]))
    except (TypeError, ValueError):
        return float(DEFAULTS[key])


def _message(pct: int, tokens: int, window: int, threshold: int, reminder: bool) -> str:
    head = (f"CONTEXT HANDOFF{' (reminder: auto-compaction is near)' if reminder else ''}: this session's "
            f"context is {pct}% full ({tokens:,} of {window:,} tokens). Project policy (CLAUDE.md, Context "
            "handoff): stop taking on new work and hand off now.")
    return "\n".join([
        head,
        f"1. Confirm with mcp__ccd_session_mgmt__get_usage; if it reports under {threshold}%, ignore this.",
        "2. Reach a safe point: finish or checkpoint the current step; start no new long job. List every "
        "background job still running (Ollama runs, subagents): the next session must not start a second "
        "Ollama job while one runs.",
        "3. Update HANDOFF.md (state, what this session did, in-flight work, next steps, open decisions) and "
        "commit it with any finished work.",
        "4. Start the continuation as a regular session when this app offers one: ToolSearch \"start_session\"; "
        "if mcp__ccd_session_mgmt__start_session (or hand_off_to_session) exists, start a local session in this "
        "folder with this session's model, effort and permission mode and the first prompt \"Read HANDOFF.md and "
        "CLAUDE.md, then continue.\", then detach_session it so it outlives this one. Otherwise run the routine: "
        f"mcp__scheduled-tasks__run_scheduled_task with taskId \"{ROUTINES[0]}\"; if it is refused because that "
        f"routine has a run in progress (this session), use \"{ROUTINES[1]}\". If none can start, ask the user "
        "to open a new chat (Ctrl+N) with: Read HANDOFF.md and CLAUDE.md, then continue.",
        "5. Reply with one line linking the new session, then end this turn. Do no further work here.",
    ])


def handle(payload, env: dict, state_dir: Path) -> dict | None:
    """The hook's JSON reply for one event, or None to stay silent."""
    if not isinstance(payload, dict) or env.get("CONTEXT_HANDOFF_OFF") == "1":
        return None
    event, session = payload.get("hook_event_name"), str(payload.get("session_id") or "")
    if event not in ("PostToolUse", "Stop", "UserPromptSubmit") or not session:
        return None
    if event == "Stop" and payload.get("stop_hook_active"):
        return None
    try:
        tokens = context_tokens(Path(str(payload.get("transcript_path") or "")))
    except OSError:
        return None
    if tokens is None:
        return None
    window = _number(env, "CONTEXT_HANDOFF_WINDOW")
    threshold, remind = _number(env, "CONTEXT_HANDOFF_PCT"), _number(env, "CONTEXT_HANDOFF_REMIND_PCT")
    pct = 100 * tokens / window if window > 0 else 0
    state_file = state_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', session)}.json"
    try:
        fired = set(json.loads(state_file.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        fired = set()
    level = "remind" if pct >= remind and "remind" not in fired else None
    if level is None and pct >= threshold and "handoff" not in fired:
        level = "handoff"
    if level is None:
        return None
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(sorted(fired | {"handoff", level})), encoding="utf-8")
    except OSError:
        pass  # without state it may repeat; still better than staying silent at the threshold
    text = _message(int(pct), tokens, int(window), int(threshold), reminder=level == "remind" and "handoff" in fired)
    note = f"Context {int(pct)}% full: handing off to a new session (HANDOFF.md)."
    if event == "Stop":
        return {"decision": "block", "reason": text, "systemMessage": note}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}, "systemMessage": note}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
        state_dir = Path(os.environ.get("CONTEXT_HANDOFF_STATE_DIR")
                         or Path(tempfile.gettempdir()) / "claude-context-handoff")
        out = handle(payload, dict(os.environ), state_dir)
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
