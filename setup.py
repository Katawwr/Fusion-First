"""Build shim (metadata lives in pyproject.toml).

The engine reads committed corpora — datasets/, cassettes/, crosswalk/, evals/ — that live at the
repo TOP LEVEL (the Modal image mounts them from there, so they are not moved into the package). To
make a bare `pip install fusion-safety` carry them too, this build step copies them into
`fusion/_bundled/` at build time; `fusion/_data.py` then finds either the top-level copy (checkout /
Modal) or the bundled copy (installed wheel).

The built web app (`frontend/dist`, from `npm --prefix frontend run build`) is copied to
`fusion/_bundled/web/` the same way, so `fusion serve` works from a bare install.
"""

from __future__ import annotations

import pathlib
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

_DATA_DIRS = ("datasets", "cassettes", "crosswalk", "evals")


class BundleData(build_py):
    def run(self):
        root = pathlib.Path(__file__).parent.resolve()
        dest = root / "fusion" / "_bundled"
        for name in _DATA_DIRS:
            src = root / name
            if src.exists():
                shutil.copytree(
                    src,
                    dest / name,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("scratch", "__pycache__", "*.pyc"),
                )
        web = root / "frontend" / "dist"
        if (web / "index.html").exists():
            # Replace, don't merge: each frontend build has new hashed asset names. A failed delete
            # (a locked file) fails the build loudly rather than shipping stale assets.
            if (dest / "web").exists():
                shutil.rmtree(dest / "web")
            shutil.copytree(web, dest / "web")
        super().run()


setup(cmdclass={"build_py": BundleData})
