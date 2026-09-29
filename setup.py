"""Build shim (metadata lives in pyproject.toml).

The engine reads committed corpora — datasets/, cassettes/, crosswalk/, evals/ — that live at the
repo TOP LEVEL (the Modal image mounts them from there, so they are not moved into the package). To
make a bare `pip install fusion-safety` carry them too, this build step copies them into
`fusion/_bundled/` at build time; `fusion/_data.py` then finds either the top-level copy (checkout /
Modal) or the bundled copy (installed wheel).

The built web app (`frontend/dist`, from `npm --prefix frontend run build`) is copied to
`fusion/_bundled/web/` the same way, so `fusion serve` works from a bare install, and so is the
Claude Code plugin marketplace (`.claude-plugin/` + `plugins/`, to `fusion/_bundled/marketplace/`),
so `claude plugin marketplace add "$(fusion plugin-dir)"` works without a checkout.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import sys

from setuptools import setup
from setuptools.command.build_py import build_py

_DATA_DIRS = ("datasets", "cassettes", "crosswalk", "evals")
_MARKETPLACE_DIRS = (".claude-plugin", "plugins")
_SKIP = shutil.ignore_patterns("scratch", "__pycache__", "*.pyc")


def _clear_read_only_and_retry(func, path, _exc):
    # OneDrive marks folders read-only, copytree copies that, and Windows won't delete them.
    for p in (path, os.path.dirname(path)):
        try:
            os.chmod(p, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        except OSError:
            pass
    func(path)  # still failing (a locked file) fails the build loudly


def _rmtree(path: pathlib.Path) -> None:
    if path.exists():
        handler = "onexc" if sys.version_info >= (3, 12) else "onerror"
        shutil.rmtree(path, **{handler: _clear_read_only_and_retry})


def replace_tree(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Replace, don't merge: each frontend build has new hashed asset names. A failed delete (a
    locked file) fails the build loudly rather than shipping stale assets."""
    _rmtree(dst)
    shutil.copytree(src, dst)


def bundle(root: pathlib.Path, dest: pathlib.Path) -> None:
    for name in _DATA_DIRS:
        src = root / name
        if src.exists():
            shutil.copytree(src, dest / name, dirs_exist_ok=True, ignore=_SKIP)
    web = root / "frontend" / "dist"
    if (web / "index.html").exists():
        replace_tree(web, dest / "web")
    if (root / ".claude-plugin" / "marketplace.json").exists():
        _rmtree(dest / "marketplace")  # a plugin file removed at the source must not linger
        for name in _MARKETPLACE_DIRS:
            shutil.copytree(root / name, dest / "marketplace" / name, ignore=_SKIP)


class BundleData(build_py):
    def run(self):
        root = pathlib.Path(__file__).parent.resolve()
        bundle(root, root / "fusion" / "_bundled")
        super().run()


if __name__ == "__main__":  # how setuptools runs this file; tests import it without building
    setup(cmdclass={"build_py": BundleData})
