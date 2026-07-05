"""PreToolUse hook: block `modal deploy` when the accuracy eval gate is red.

Reads the tool call JSON on stdin. If it is a Bash `modal deploy`, run the eval gate strictly;
a real regression exits 2 (which Claude Code treats as 'deny this tool call'). Everything else
is allowed through (exit 0). The gate is advisory only while no baseline exists yet.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read_command() -> str:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return ""
    return (data.get("tool_input", {}) or {}).get("command", "") or ""


def main() -> int:
    command = _read_command()
    if "modal deploy" not in command:
        return 0  # not a deploy; allow

    try:
        p = subprocess.run(
            [sys.executable, "scripts/fusion_cli.py", "eval", "--check", "direct_prompt_injection"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001 - do not hard-fail the deploy on hook error
        print(f"pre-deploy gate could not run ({e}); allowing deploy", file=sys.stderr)
        return 0

    summary = next((ln for ln in p.stdout.splitlines() if ln.startswith("[eval:")), p.stdout.strip())
    if p.returncode != 0:
        print(f"BLOCKED: accuracy gate is red, refusing deploy.\n{summary}", file=sys.stderr)
        return 2  # deny the tool call
    print(f"pre-deploy gate green: {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
