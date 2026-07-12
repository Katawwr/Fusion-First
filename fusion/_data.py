"""Locate the committed data corpora — datasets/, cassettes/, crosswalk/, evals/.

Source of truth is the repo top level (which is also how the Modal image mounts them, so it is NOT
moved into the package). Resolution order:

  1. ``FUSION_DATA_DIR`` — explicit override; point it at the directory that CONTAINS datasets/ etc.
  2. repo checkout / Modal mount — the parent of the ``fusion`` package.
  3. bundled copy inside the wheel (``fusion/_bundled/``) — populated at build time, so a bare
     ``pip install fusion-safety`` has the corpora with no checkout.

Every module reads its data dir through :func:`data_root`, so all of the above just work.
"""

from __future__ import annotations

import os
import pathlib

_MARKERS = ("datasets", "crosswalk", "cassettes")


def _has_data(root: pathlib.Path) -> bool:
    return any((root / m).exists() for m in _MARKERS)


def data_root() -> pathlib.Path:
    env = os.environ.get("FUSION_DATA_DIR")
    if env:
        return pathlib.Path(env)
    repo = pathlib.Path(__file__).resolve().parent.parent  # <repo>/ (parent of the fusion package)
    if _has_data(repo):
        return repo
    bundled = pathlib.Path(__file__).resolve().parent / "_bundled"
    if _has_data(bundled):
        return bundled
    return repo  # nothing found — let the caller raise a clear FileNotFoundError on first read
