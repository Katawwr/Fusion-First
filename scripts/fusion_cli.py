"""Run the `fusion` CLI (`fusion_first/cli.py`) from a checkout: `python scripts/fusion_cli.py ...`."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fusion_first.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
