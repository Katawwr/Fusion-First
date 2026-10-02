"""Build shim (metadata lives in pyproject.toml).

Copies the runtime data the installed tool reads (from the top-level datasets/, cassettes/, crosswalk/,
evals/), the built web app and the plugin marketplace into `fusion_first/_bundled/`, which
`fusion_first/_data.py` falls back to outside a checkout. Dev-only modules are left out.
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
# What the installed tool reads through data_root(); the rest of these directories is evidence for
# scripts/ and tests. MANIFEST.in lists the same files for the sdist.
_RUNTIME_DATA = (
    "cassettes/*.json",
    "crosswalk/*.yaml",
    "datasets/gold/*.jsonl",
    "datasets/probes/*.jsonl",
    "datasets/guard_bench/cases.jsonl",
    "datasets/quality_tests/*.jsonl",
    "datasets/reference_agents/*.jsonl",
    "evals/policy.yaml",
    "evals/baseline.*.json",
    "evals/guard_bench.baseline.json",
    "evals/validation/v1/judge_eval_prob_qwen7b.json",
)
_MARKETPLACE_DIRS = (".claude-plugin", "plugins")
_SKIP = shutil.ignore_patterns("scratch", "__pycache__", "*.pyc")
_SKIP_PLUGIN_DOCS = shutil.ignore_patterns("__pycache__", "*.pyc", "README.md")
# Modules no installed entry point reaches; tests/test_packaging.py re-derives this set from the import graph.
DEV_ONLY_MODULES = frozenset({
    "fusion_first.attacks.adaptive",
    "fusion_first.stats.calibration_metrics",
    "fusion_first.stats.power",
    "fusion_first.validate.analysis",
    "fusion_first.validate.b3",
    "fusion_first.validate.baselines",
    "fusion_first.validate.benign_actions",
    "fusion_first.validate.claims",
    "fusion_first.validate.experiments",
    "fusion_first.validate.guard_heldout",
    "fusion_first.validate.guard_on_transcripts",
    "fusion_first.validate.importers",
    "fusion_first.validate.importers.bipia",
    "fusion_first.validate.importers.deepset",
    "fusion_first.validate.importers.gandalf",
    "fusion_first.validate.importers.ifeval",
    "fusion_first.validate.importers.injecagent",
    "fusion_first.validate.importers.xstest",
    "fusion_first.validate.judge_eval",
    "fusion_first.validate.llama_guard",
    "fusion_first.validate.seal",
    "fusion_first.validate.transcripts",
    "fusion_first.validate.trust_report",
    "fusion_first.validate.value_ledger",
})


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


def replace_tree(src: pathlib.Path, dst: pathlib.Path, ignore=None) -> None:
    """Replace, don't merge: each frontend build has new hashed asset names."""
    _rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def bundle(root: pathlib.Path, dest: pathlib.Path, *, require: bool = True) -> None:
    """Copy what a bare install needs into `dest`. `require`: fail without the web app or the marketplace."""
    web = root / "frontend" / "dist"
    market = root / ".claude-plugin" / "marketplace.json"
    missing = [what for what, there in (("the built web app, frontend/dist (npm --prefix frontend run build)",
                                         (web / "index.html").exists()),
                                        ("the plugin marketplace, .claude-plugin/marketplace.json", market.exists()))
               if not there]
    if require and missing:
        raise SystemExit(f"fusion-safety build: missing {' and '.join(missing)}. "
                         "Set FUSION_PARTIAL_BUILD=1 for a development build without them.")
    for name in _DATA_DIRS:
        _rmtree(dest / name)
    for pattern in _RUNTIME_DATA:
        for src in sorted(root.glob(pattern)):
            target = dest / src.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
    if (web / "index.html").exists():  # the social-preview image is served from the live site, not locally
        replace_tree(web, dest / "web", ignore=shutil.ignore_patterns("og-image.png"))
    if market.exists():
        _rmtree(dest / "marketplace")
        for name in _MARKETPLACE_DIRS:
            shutil.copytree(root / name, dest / "marketplace" / name, ignore=_SKIP_PLUGIN_DOCS)


class BundleData(build_py):
    def run(self):
        if not getattr(self, "editable_mode", False):  # an editable install reads the checkout itself
            root = pathlib.Path(__file__).parent.resolve()
            bundle(root, root / "fusion_first" / "_bundled", require=not os.environ.get("FUSION_PARTIAL_BUILD"))
        super().run()

    def find_package_modules(self, package, package_dir):
        # The sdist lists its sources through here too.
        return [(pkg, mod, path) for pkg, mod, path in super().find_package_modules(package, package_dir)
                if (pkg if mod == "__init__" else f"{pkg}.{mod}") not in DEV_ONLY_MODULES]


if __name__ == "__main__":  # how setuptools runs this file; tests import it without building
    setup(cmdclass={"build_py": BundleData})
