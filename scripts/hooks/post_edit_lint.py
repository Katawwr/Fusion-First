"""PostToolUse hook: lint a just-edited Python file with ruff (informational).

Reads the tool call JSON on stdin, finds the edited file, and if it is a tracked .py file runs
ruff on it and prints any findings. Always exits 0 — this nudges, it does not block.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    fp = (data.get("tool_input", {}) or {}).get("file_path", "")
    if not fp or not fp.endswith(".py"):
        return 0
    p = Path(fp)
    try:
        rel = p.resolve().relative_to(ROOT)
    except ValueError:
        return 0
    if rel.parts and rel.parts[0] not in {"fusion_first", "tests", "scripts", "app"}:
        return 0
    try:
        r = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(p)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        return 0
    if r.returncode != 0:
        print(f"ruff findings in {rel}:\n{r.stdout.strip()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
