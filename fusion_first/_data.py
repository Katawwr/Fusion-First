"""Locate the committed data corpora: datasets/, cassettes/, crosswalk/, evals/.

Source of truth is the repo top level (which is also how the Modal image mounts them, so it is NOT
moved into the package). Resolution order:

  1. ``FUSION_DATA_DIR``: explicit override; point it at the directory that CONTAINS datasets/ etc.
  2. repo checkout / Modal mount: the parent of the ``fusion_first`` package.
  3. bundled copy inside the wheel (``fusion_first/_bundled/``): populated at build time, so a bare
     ``pip install fusion-safety`` has the corpora with no checkout.

A root is recognised by Fusion's own crosswalk file, never by generic names: an installed package's
parent is site-packages, where Hugging Face's ``datasets`` package lives.

Every module reads its data dir through :func:`data_root`, so all of the above just work.
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
    for root in (pkg.parent, pkg / "_bundled"):  # the checkout, then the copy bundled in the wheel
        if _has_data(root):
            return root
    return pkg.parent  # nothing found — let the caller raise a clear FileNotFoundError on first read


def is_installed_copy() -> bool:
    """The corpora are the copy bundled in an installed wheel (inside site-packages): commands that rewrite
    them (record, --update-baseline) refuse there."""
    return data_root() == pathlib.Path(__file__).resolve().parent / "_bundled"


def _is_our_marketplace(root: pathlib.Path) -> bool:
    try:
        manifest = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(manifest, dict) and manifest.get("name") == MARKETPLACE_NAME


def plugin_root(pkg_dir: pathlib.Path | None = None) -> pathlib.Path | None:
    """The Claude Code plugin marketplace (``.claude-plugin/marketplace.json`` + ``plugins/``): the
    checkout, else the copy bundled in the wheel; None when neither is there."""
    pkg = pkg_dir or pathlib.Path(__file__).resolve().parent
    for root in (pkg.parent, pkg / "_bundled" / "marketplace"):
        if _is_our_marketplace(root):
            return root
    return None
