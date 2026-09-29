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

    _load_setup().bundle(root, dest)

    assert _files(dest / "marketplace") == sorted(files)


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory) -> list[str]:
    """The file names in a wheel built for real from a copy of the project (no corpora: faster)."""
    tmp = tmp_path_factory.mktemp("wheel")
    proj = tmp / "proj"
    proj.mkdir()
    for rel in ("pyproject.toml", "setup.py", "MANIFEST.in", "README.md"):
        shutil.copy2(ROOT / rel, proj / rel)
    skip = shutil.ignore_patterns("_bundled", "__pycache__", "*.pyc")
    shutil.copytree(ROOT / "fusion", proj / "fusion", ignore=skip)
    shutil.copytree(ROOT / "plugins", proj / "plugins", ignore=skip)
    shutil.copytree(ROOT / ".claude-plugin", proj / ".claude-plugin")
    out = tmp / "dist"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", str(proj), "--no-deps",
                        "--no-build-isolation", "-q", "-w", str(out)],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    (wheel,) = out.glob("fusion_safety-*.whl")
    return zipfile.ZipFile(wheel).namelist()


@pytest.mark.integration
def test_the_wheel_ships_the_plugin_marketplace(wheel_names):
    """Package-data globs skip dot-paths (.claude-plugin/, .mcp.json) unless they are named, and a
    plugin without them does not load."""
    prefix = "fusion/_bundled/marketplace/"
    shipped = sorted(n[len(prefix):] for n in wheel_names if n.startswith(prefix))
    source = sorted(p.relative_to(ROOT).as_posix()
                    for d in ("plugins", ".claude-plugin") for p in (ROOT / d).rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts)
    assert shipped == source


@pytest.mark.integration
def test_the_wheel_ships_the_package_s_own_data_files(wheel_names):
    """Code reads non-Python files that sit next to it (fusion/model/models.yaml: without it every
    installed `fusion doctor` and run crashes); package-data must name each one."""
    source = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "fusion").rglob("*")
                    if p.is_file() and p.suffix not in (".py", ".pyc")
                    and "_bundled" not in p.parts and "__pycache__" not in p.parts)
    assert source
    assert [s for s in source if s not in wheel_names] == []


@pytest.mark.unit
def test_plugin_root_is_the_checkout_in_a_source_tree():
    from fusion._data import plugin_root

    root = plugin_root()

    assert root == ROOT
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert {p["name"] for p in market["plugins"]} == {"fusion", "fusion-guard"}


@pytest.mark.unit
def test_plugin_root_falls_back_to_the_bundled_copy(tmp_path):
    from fusion._data import plugin_root

    pkg = tmp_path / "site-packages" / "fusion"
    pkg.mkdir(parents=True)
    assert plugin_root(pkg) is None
    _write(pkg / "_bundled/marketplace/.claude-plugin/marketplace.json", "{}")

    assert plugin_root(pkg) == pkg / "_bundled" / "marketplace"


@pytest.mark.unit
def test_cli_plugin_dir_prints_the_marketplace(capsys):
    from fusion.cli import main

    assert main(["plugin-dir"]) == 0
    assert capsys.readouterr().out.strip() == str(ROOT)


@pytest.mark.unit
def test_cli_plugin_dir_without_a_marketplace_fails_with_the_install_line(monkeypatch, capsys):
    import fusion._data
    from fusion.cli import main

    monkeypatch.setattr(fusion._data, "plugin_root", lambda pkg_dir=None: None)

    assert main(["plugin-dir"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "pip install fusion-safety" in captured.err


@pytest.mark.unit
def test_one_version_for_the_package_the_app_and_the_plugin_pin():
    import tomllib

    import fusion

    assert tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] == fusion.__version__


@pytest.mark.unit
def test_a_pip_installed_web_app_reports_its_release_not_dev(monkeypatch):
    """Modal sets VERSION; a `fusion serve` from a pip install has none, and "dev" names no release."""
    pytest.importorskip("pydantic_settings")
    import fusion
    from fusion.web.settings import Settings

    monkeypatch.delenv("VERSION", raising=False)
    assert Settings().version == fusion.__version__
    monkeypatch.setenv("VERSION", "rebuild-abc1234")
    assert Settings().version == "rebuild-abc1234"
