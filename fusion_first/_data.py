"""Locate the data corpora (datasets/, cassettes/, crosswalk/, evals/).

Order: ``FUSION_DATA_DIR``, the repo checkout (parent of the package), then the copy bundled in the
wheel (``fusion_first/_bundled/``). A root is recognised by Fusion's own crosswalk file, never by
generic names: an installed package's parent is site-packages, where HF's ``datasets`` lives.
"""

from __future__ import annotations

import json
import os
import pathlib

_CORPUS_MARKER = "crosswalk/owasp_crosswalk.*.yaml"
MARKETPLACE_NAME = "fusion-first"


def _has_data(root: pathlib.Path) -> bool:
    return any(root.glob(_CORPUS_MARKER))


def data_root(pkg_dir: pathlib.Path | None = None) -> pathlib.Path:
    env = os.environ.get("FUSION_DATA_DIR")
    if env:
        return pathlib.Path(env)
    pkg = pkg_dir or pathlib.Path(__file__).resolve().parent
    for root in (pkg.parent, pkg / "_bundled"):
        if _has_data(root):
            return root
    return pkg.parent  # nothing found: the caller raises FileNotFoundError on first read


def is_installed_copy() -> bool:
    """The corpora are the wheel's bundled copy: commands that rewrite them refuse there."""
    return data_root() == pathlib.Path(__file__).resolve().parent / "_bundled"


def _is_our_marketplace(root: pathlib.Path) -> bool:
    try:
        manifest = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(manifest, dict) and manifest.get("name") == MARKETPLACE_NAME


def plugin_root(pkg_dir: pathlib.Path | None = None) -> pathlib.Path | None:
    """The Claude Code plugin marketplace root: the checkout, else the wheel's bundled copy, else None."""
    pkg = pkg_dir or pathlib.Path(__file__).resolve().parent
    for root in (pkg.parent, pkg / "_bundled" / "marketplace"):
        if _is_our_marketplace(root):
            return root
    return None
