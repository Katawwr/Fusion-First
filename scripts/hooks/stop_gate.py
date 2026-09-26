"""Stop hook: run the fast unit tests + the accuracy eval gate and report a concise summary.

Advisory by design — it prints status and always exits 0, so it never traps the session. The
blocking gate lives in pre_deploy_gate.py. Kept resilient: any failure here degrades to a note.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, encoding="utf-8"
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001 - hook must never raise
        return 1, f"(hook could not run {' '.join(cmd)}: {e})"


def main() -> int:
    lines = ["Fusion Stop gate:"]

    code, out = _run([sys.executable, "-m", "pytest", "-m", "unit", "-q"], timeout=120)
    tail = [ln for ln in out.strip().splitlines() if ln.strip()]
    lines.append(f"  unit tests: {'PASS' if code == 0 else 'FAIL'} ({tail[-1] if tail else 'no output'})")

    code, out = _run(
        [sys.executable, "scripts/fusion_cli.py", "eval", "--check", "all"],
        timeout=120,
    )
    evals = [ln for ln in out.splitlines() if ln.startswith("[eval:")] or [out.strip()[:200]]
    lines.extend(f"  {ln}" for ln in evals)

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
