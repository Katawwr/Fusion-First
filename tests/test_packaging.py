"""The published package: the build step bundles what a bare `pip install fusion-safety` needs (the
Claude Code plugin marketplace included), and `fusion plugin-dir` finds it."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_setup():
    """setup.py as a module; its `setup()` call only runs as __main__ (how setuptools executes it)."""
    spec = importlib.util.spec_from_file_location("fusion_setup", ROOT / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _files(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _read_only(path: pathlib.Path) -> None:
    os.chmod(path, stat.S_IREAD | stat.S_IEXEC)  # Windows: the read-only attribute; POSIX: r-x


@pytest.mark.unit
def test_bundling_replaces_a_read_only_tree(tmp_path):
    """OneDrive marks folders read-only and copytree copies that onto the bundled copy, so the next
    build must still replace it (Windows refuses to delete a read-only directory)."""
    src = tmp_path / "dist"
    _write(src / "index.html", "new")
    _write(src / "assets" / "app-new.js", "new")
    dst = tmp_path / "bundled" / "web"
    _write(dst / "assets" / "app-old.js", "old")
    _read_only(dst / "assets")
    _read_only(dst)

    _load_setup().replace_tree(src, dst)

    assert _files(dst) == ["assets/app-new.js", "index.html"]


@pytest.mark.unit
def test_bundling_copies_the_plugin_marketplace(tmp_path):
    root = tmp_path / "repo"
    files = {
        ".claude-plugin/marketplace.json": '{"name": "m", "plugins": []}',
        "plugins/p/.claude-plugin/plugin.json": '{"name": "p"}',
        "plugins/p/.mcp.json": "{}",
        "plugins/p/skills/s/SKILL.md": "---\nname: s\n---\n",
    }
    for rel, text in files.items():
        _write(root / rel, text)
    _write(root / "plugins/p/__pycache__/x.cpython-313.pyc", "")
    dest = tmp_path / "bundled"
    _write(dest / "marketplace/plugins/removed/README.md", "stale")

    _load_setup().bundle(root, dest, require=False)

    assert _files(dest / "marketplace") == sorted(files)


def _release_tree(root: pathlib.Path) -> None:
    """What a release build needs besides the corpora: the built web app and our marketplace."""
    _write(root / "frontend/dist/index.html", "<html></html>")
    _write(root / ".claude-plugin/marketplace.json", '{"name": "fusion-first", "plugins": []}')
    _write(root / "plugins/fusion/.claude-plugin/plugin.json", '{"name": "fusion"}')


RUNTIME_DATA = ["datasets/gold/x.v1.jsonl", "datasets/probes/x.v1.jsonl", "datasets/guard_bench/cases.jsonl",
                "datasets/quality_tests/instruction_following.v1.jsonl", "crosswalk/owasp_crosswalk.v2025.yaml",
                "cassettes/x.v1.json", "evals/x.baseline.json", "evals/validation/v1/judge_eval_prob_qwen7b.json"]
# Third-party sets (licensed per source; ATTRIBUTION.md holds their notices), raw downloads, the Claude
# Code held-out sets and evidence transcripts: read only by scripts/ and tests, never by the installed tool.
EVIDENCE_ONLY = ["datasets/external/injecagent.v1.jsonl", "datasets/external/ATTRIBUTION.md",
                 "datasets/external/raw/ifeval/ifeval_input_data.jsonl",
                 "datasets/guard_bench/claude_code.jsonl", "datasets/guard_bench/claude_code_heldout_v3.jsonl",
                 "evals/validation/v1/transcripts/llama.jsonl"]


@pytest.mark.unit
def test_bundling_ships_runtime_data_only_and_drops_what_the_source_removed(tmp_path):
    root = tmp_path / "repo"
    _release_tree(root)
    for rel in RUNTIME_DATA + EVIDENCE_ONLY:
        _write(root / rel, "x")
    dest = tmp_path / "bundled"
    _write(dest / "datasets/gold/removed_check.v1.jsonl", "stale")  # from an earlier build

    _load_setup().bundle(root, dest)

    shipped = set(_files(dest))
    assert set(RUNTIME_DATA) <= shipped
    assert shipped.isdisjoint(EVIDENCE_ONLY)
    assert "datasets/gold/removed_check.v1.jsonl" not in shipped


@pytest.mark.unit
def test_a_release_build_without_the_web_app_or_the_marketplace_fails_loudly(tmp_path):
    """Built from a fresh clone (frontend/dist is not in git) the wheel silently had no web app, and
    `fusion serve` from PyPI would tell users to run npm."""
    setup_mod = _load_setup()
    root = tmp_path / "repo"
    _release_tree(root)
    (root / "frontend/dist/index.html").unlink()
    with pytest.raises(SystemExit, match="frontend/dist"):
        setup_mod.bundle(root, tmp_path / "b1")
    _release_tree(root)
    (root / ".claude-plugin/marketplace.json").unlink()
    with pytest.raises(SystemExit, match="marketplace"):
        setup_mod.bundle(root, tmp_path / "b2")
    setup_mod.bundle(root, tmp_path / "b3", require=False)  # a development build may skip them


@pytest.mark.integration
def test_the_sdist_leaves_out_evidence_only_data(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    for rel in ("pyproject.toml", "setup.py", "MANIFEST.in", "README.md"):
        shutil.copy2(ROOT / rel, proj / rel)
    shutil.copytree(ROOT / "fusion_first", proj / "fusion_first",
                    ignore=shutil.ignore_patterns("_bundled", "__pycache__", "*.pyc"))
    for rel in RUNTIME_DATA + EVIDENCE_ONLY:
        _write(proj / rel, "x")
    for rel in ("CLAUDE.md", "SCHEMA.md"):
        _write(proj / rel, "x")

    r = subprocess.run([sys.executable, "setup.py", "-q", "sdist", "-d", str(tmp_path / "out")], cwd=proj,
                       capture_output=True, text=True, timeout=600)

    assert r.returncode == 0, r.stderr[-3000:]
    (sdist,) = (tmp_path / "out").glob("fusion_safety-*.tar.gz")
    with tarfile.open(sdist) as tar:
        names = {n.split("/", 1)[1] for n in tar.getnames() if "/" in n}
    assert {"datasets/gold/x.v1.jsonl", "crosswalk/owasp_crosswalk.v2025.yaml"} <= names
    assert names.isdisjoint(EVIDENCE_ONLY)


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory) -> list[str]:
    """The file names in a wheel built for real from a copy of the project (no corpora: faster)."""
    tmp = tmp_path_factory.mktemp("wheel")
    proj = tmp / "proj"
    proj.mkdir()
    for rel in ("pyproject.toml", "setup.py", "MANIFEST.in", "README.md"):
        shutil.copy2(ROOT / rel, proj / rel)
    skip = shutil.ignore_patterns("_bundled", "__pycache__", "*.pyc")
    shutil.copytree(ROOT / "fusion_first", proj / "fusion_first", ignore=skip)
    shutil.copytree(ROOT / "plugins", proj / "plugins", ignore=skip)
    shutil.copytree(ROOT / ".claude-plugin", proj / ".claude-plugin")
    out = tmp / "dist"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", str(proj), "--no-deps",
                        "--no-build-isolation", "-q", "-w", str(out)],
                       capture_output=True, text=True, timeout=600,
                       env={**os.environ, "FUSION_PARTIAL_BUILD": "1"})  # no web app in this copy
    assert r.returncode == 0, r.stderr[-3000:]
    (wheel,) = out.glob("fusion_safety-*.whl")
    return zipfile.ZipFile(wheel).namelist()


@pytest.mark.integration
def test_the_wheel_ships_the_plugin_marketplace(wheel_names):
    """Package-data globs skip dot-paths (.claude-plugin/, .mcp.json) unless they are named, and a
    plugin without them does not load."""
    prefix = "fusion_first/_bundled/marketplace/"
    shipped = sorted(n[len(prefix):] for n in wheel_names if n.startswith(prefix))
    source = sorted(p.relative_to(ROOT).as_posix()
                    for d in ("plugins", ".claude-plugin") for p in (ROOT / d).rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts)
    assert shipped == source


@pytest.mark.integration
def test_the_wheel_ships_the_package_s_own_data_files(wheel_names):
    """Code reads non-Python files that sit next to it (fusion_first/model/models.yaml: without it every
    installed `fusion doctor` and run crashes); package-data must name each one."""
    source = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "fusion_first").rglob("*")
                    if p.is_file() and p.suffix not in (".py", ".pyc")
                    and "_bundled" not in p.parts and "__pycache__" not in p.parts)
    assert source
    assert [s for s in source if s not in wheel_names] == []


@pytest.mark.unit
def test_plugin_root_is_the_checkout_in_a_source_tree():
    from fusion_first._data import plugin_root

    root = plugin_root()

    assert root == ROOT
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert {p["name"] for p in market["plugins"]} == {"fusion", "fusion-guard"}


@pytest.mark.unit
def test_plugin_root_falls_back_to_the_bundled_copy(tmp_path):
    from fusion_first._data import plugin_root

    pkg = tmp_path / "site-packages" / "fusion_first"
    pkg.mkdir(parents=True)
    assert plugin_root(pkg) is None
    _write(pkg / "_bundled/marketplace/.claude-plugin/marketplace.json", '{"name": "fusion-first"}')

    assert plugin_root(pkg) == pkg / "_bundled" / "marketplace"


@pytest.mark.unit
def test_plugin_root_ignores_another_marketplace_in_site_packages(tmp_path):
    from fusion_first._data import plugin_root

    site = tmp_path / "site-packages"
    _write(site / ".claude-plugin/marketplace.json", '{"name": "someone-else", "plugins": []}')
    pkg = site / "fusion_first"
    _write(pkg / "_bundled/marketplace/.claude-plugin/marketplace.json", '{"name": "fusion-first", "plugins": []}')

    assert plugin_root(pkg) == pkg / "_bundled" / "marketplace"


@pytest.mark.unit
def test_data_root_is_the_checkout_in_a_source_tree():
    from fusion_first._data import data_root

    assert data_root() == ROOT


@pytest.mark.unit
def test_data_root_ignores_a_site_packages_that_holds_other_datasets(tmp_path):
    """Hugging Face's `datasets` installs site-packages/datasets/ (lm-eval, evaluate and trl pull it in):
    an installed wheel took that for a checkout and every corpus read failed."""
    from fusion_first._data import data_root

    site = tmp_path / "site-packages"
    _write(site / "datasets/__init__.py", "")
    pkg = site / "fusion_first"
    _write(pkg / "_bundled/crosswalk/owasp_crosswalk.v2025.yaml", "codes: {}")

    assert data_root(pkg) == pkg / "_bundled"


@pytest.mark.unit
def test_cli_plugin_dir_prints_the_marketplace(capsys):
    from fusion_first.cli import main

    assert main(["plugin-dir"]) == 0
    assert capsys.readouterr().out.strip() == str(ROOT)


@pytest.mark.unit
def test_cli_plugin_dir_without_a_marketplace_fails_with_the_install_line(monkeypatch, capsys):
    import fusion_first._data
    from fusion_first.cli import main

    monkeypatch.setattr(fusion_first._data, "plugin_root", lambda pkg_dir=None: None)

    assert main(["plugin-dir"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "pip install fusion-safety" in captured.err


@pytest.mark.unit
def test_one_version_for_the_package_the_app_and_the_plugin_pin():
    import tomllib

    import fusion_first

    assert tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] == fusion_first.__version__


@pytest.mark.unit
def test_a_pip_installed_web_app_reports_its_release_not_dev(monkeypatch):
    """Modal sets VERSION; a `fusion serve` from a pip install has none, and "dev" names no release."""
    pytest.importorskip("pydantic_settings")
    import fusion_first
    from fusion_first.web.settings import Settings

    monkeypatch.delenv("VERSION", raising=False)
    assert Settings().version == fusion_first.__version__
    monkeypatch.setenv("VERSION", "rebuild-abc1234")
    assert Settings().version == "rebuild-abc1234"
