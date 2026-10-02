"""Backwards-compatible shim: the CLI now lives in the installed package at `fusion_first/cli.py`
(so `pip install fusion-safety` gives you the `fusion` command). This keeps the historical
`python scripts/fusion_cli.py …` invocations (docs, hooks, CI examples) working from a checkout.
"""

from __future__ import annotations

import pathlib
import sys

# Allow running as a plain script from a source checkout (no install needed).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fusion_first.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
