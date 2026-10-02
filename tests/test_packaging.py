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
    _write(root / "plugins/p/README.md", "docs for people, not a plugin file")
    dest = tmp_path / "bundled"
    _write(dest / "marketplace/plugins/removed/README.md", "stale")

    _load_setup().bundle(root, dest, require=False)

    assert _files(dest / "marketplace") == sorted(files)


def _release_tree(root: pathlib.Path) -> None:
    """What a release build needs besides the corpora: the built web app and our marketplace."""
    _write(root / "frontend/dist/index.html", "<html></html>")
    _write(root / ".claude-plugin/marketplace.json", '{"name": "fusion-first", "plugins": []}')
    _write(root / "plugins/fusion/.claude-plugin/plugin.json", '{"name": "fusion"}')


# What the installed tool reads through data_root() (goldset, taxonomy, guard benchmark, gate, measure,
# demo cassettes, the local-grader evidence behind the doctor hint).
RUNTIME_DATA = sorted(["cassettes/x.v1.json", "crosswalk/owasp_crosswalk.v2025.yaml",
                       "datasets/gold/x.v1.jsonl", "datasets/probes/x.v1.jsonl", "datasets/guard_bench/cases.jsonl",
                       "datasets/quality_tests/instruction_following.v1.jsonl", "datasets/reference_agents/v1.jsonl",
                       "evals/policy.yaml", "evals/baseline.x.json", "evals/guard_bench.baseline.json",
                       "evals/validation/v1/judge_eval_prob_qwen7b.json"])
# Everything else is evidence read only by scripts/ and tests: third-party sets (licensed per source) and raw
# downloads, the Claude Code held-out sets, pre-registrations, evidence reports and transcripts, the claims
# registry.
EVIDENCE_ONLY = ["datasets/external/injecagent.v1.jsonl", "datasets/external/ATTRIBUTION.md",
                 "datasets/external/raw/ifeval/ifeval_input_data.jsonl",
                 "datasets/guard_bench/claude_code.jsonl", "datasets/guard_bench/claude_code_heldout_v3.jsonl",
                 "datasets/guard_bench/PREREG_heldout_v3.md", "evals/claims.yaml",
                 "evals/guard_bench/claude_code_heldout_v1.json", "evals/validation/v1/step2_guard.json",
                 "evals/validation/v1/PREREG_step2_guard.md", "evals/validation/v1/judge_eval_prob_qwen7b/items.json",
                 "evals/validation/v1/transcripts/llama.jsonl"]


@pytest.mark.unit
def test_bundling_ships_runtime_data_only_and_drops_what_the_source_removed(tmp_path):
    root = tmp_path / "repo"
    _release_tree(root)
    for rel in RUNTIME_DATA + EVIDENCE_ONLY:
        _write(root / rel, "x")
    _write(root / "frontend/dist/og-image.png", "png")
    dest = tmp_path / "bundled"
    _write(dest / "datasets/gold/removed_check.v1.jsonl", "stale")  # from an earlier build

    _load_setup().bundle(root, dest)

    shipped = [f for f in _files(dest) if f.split("/")[0] in ("cassettes", "crosswalk", "datasets", "evals")]
    assert shipped == RUNTIME_DATA  # nothing evidence-only, nothing stale from an earlier build
    # The social-preview image is fetched from the live site's URL, never from a local `fusion serve`.
    assert _files(dest / "web") == ["index.html"]


@pytest.mark.unit
def test_a_release_build_without_the_web_app_or_the_marketplace_fails_loudly(tmp_path):
    """frontend/dist is not in git: a release built from a fresh clone must not silently ship no web app."""
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
def test_the_sdist_carries_only_what_builds_the_wheel(tmp_path):
    """No project docs, tests, examples or evidence in the sdist."""
    proj = tmp_path / "proj"
    proj.mkdir()
    for rel in ("pyproject.toml", "setup.py", "MANIFEST.in", "PYPI.md"):
        shutil.copy2(ROOT / rel, proj / rel)
    skip = shutil.ignore_patterns("_bundled", "__pycache__", "*.pyc")
    shutil.copytree(ROOT / "fusion_first", proj / "fusion_first", ignore=skip)
    shutil.copytree(ROOT / "plugins", proj / "plugins", ignore=skip)
    shutil.copytree(ROOT / ".claude-plugin", proj / ".claude-plugin")
    _write(proj / "frontend/dist/index.html", "<html></html>")
    _write(proj / "frontend/dist/og-image.png", "png")
    for rel in RUNTIME_DATA + EVIDENCE_ONLY:
        _write(proj / rel, "x")
    for rel in ("CLAUDE.md", "SCHEMA.md", "HANDOFF.md", "tests/test_x.py", "integrations/README.md",
                "integrations/examples/fusion_adapter.py", "scripts/run_evidence.py"):
        _write(proj / rel, "x")

    r = subprocess.run([sys.executable, "setup.py", "-q", "sdist", "-d", str(tmp_path / "out")], cwd=proj,
                       capture_output=True, text=True, timeout=600)

    assert r.returncode == 0, r.stderr[-3000:]
    (sdist,) = (tmp_path / "out").glob("fusion_safety-*.tar.gz")
    with tarfile.open(sdist) as tar:
        names = sorted(m.name.split("/", 1)[1] for m in tar.getmembers() if "/" in m.name and m.isfile())
    assert [n for n in names if n.split("/")[0] in ("cassettes", "crosswalk", "datasets", "evals")] == RUNTIME_DATA
    kept = ("cassettes", "crosswalk", "datasets", "evals", "fusion_first", "plugins", ".claude-plugin", "frontend",
            "fusion_safety.egg-info")
    top = ("PKG-INFO", "PYPI.md", "pyproject.toml", "setup.py", "setup.cfg", "MANIFEST.in")
    assert [n for n in names if n.split("/")[0] not in kept and n not in top] == []
    assert [n for n in names if n.endswith("README.md")] == []  # PYPI.md is the package page
    assert "frontend/dist/og-image.png" not in names
    dev = {m.replace(".", "/") for m in _load_setup().DEV_ONLY_MODULES}
    assert [n for n in names if n.endswith(".py") and n[:-3].removesuffix("/__init__") in dev] == []


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory) -> list[str]:
    """The file names in a wheel built for real from a copy of the project (no corpora: faster)."""
    tmp = tmp_path_factory.mktemp("wheel")
    proj = tmp / "proj"
    proj.mkdir()
    for rel in ("pyproject.toml", "setup.py", "MANIFEST.in", "PYPI.md"):
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
                    if p.is_file() and "__pycache__" not in p.parts and p.name != "README.md")
    assert shipped == source


@pytest.mark.integration
def test_the_wheel_ships_every_module_but_the_dev_only_ones(wheel_names):
    modules = {n[:-3].removesuffix("/__init__").replace("/", ".") for n in wheel_names
               if n.startswith("fusion_first/") and n.endswith(".py")}
    dev = set(_load_setup().DEV_ONLY_MODULES)
    assert modules.isdisjoint(dev)
    assert modules | dev == set(_package_modules())


@pytest.mark.integration
def test_the_wheel_ships_the_package_s_own_data_files(wheel_names):
    """Code reads non-Python files that sit next to it (fusion_first/model/models.yaml: without it every
    installed `fusion doctor` and run crashes); package-data must name each one."""
    source = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "fusion_first").rglob("*")
                    if p.is_file() and p.suffix not in (".py", ".pyc")
                    and "_bundled" not in p.parts and "__pycache__" not in p.parts)
    assert source
    assert [s for s in source if s not in wheel_names] == []


def _package_modules() -> dict[str, pathlib.Path]:
    out = {}
    for p in (ROOT / "fusion_first").rglob("*.py"):
        if "_bundled" in p.parts or "__pycache__" in p.parts:
            continue
        parts = list(p.relative_to(ROOT).with_suffix("").parts)
        out[".".join(parts[:-1] if parts[-1] == "__init__" else parts)] = p
    return out


def _reachable_modules() -> set[str]:
    """Every fusion_first module the installed entry points and the public library API can import (module
    level or inside functions; `from package import submodule`; import_module("fusion_first...") strings)."""
    import ast

    modules = _package_modules()

    def imports_of(name: str) -> set[str]:
        path = modules[name]
        found = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = name.split(".") if path.name == "__init__.py" else name.split(".")[:-1]
                    parts = parts[: len(parts) - (node.level - 1)]
                    base = ".".join(parts + ([node.module] if node.module else []))
                found |= {base} | {f"{base}.{a.name}" for a in node.names}
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("fusion_first."):
                found.add(node.value)
        closed = {".".join(m.split(".")[:i]) for m in found for i in range(1, m.count(".") + 2)}
        return {m for m in closed if m in modules}

    roots = {"fusion_first", "fusion_first.cli", "fusion_first.integrations.mcp_server",  # console scripts
             "fusion_first.web.factory", "fusion_first.web.serve",  # fusion serve
             "fusion_first.integrations.claude_hooks", "fusion_first.integrations.agent_tools",
             "fusion_first.integrations.promptfoo",  # promptfoo assertions load it by path
             "fusion_first.targets"} | {m for m in modules if m.startswith("fusion_first.guardrail")}  # library API
    seen, stack = set(), sorted(roots)
    while stack:
        m = stack.pop()
        if m not in seen:
            seen.add(m)
            stack.extend(imports_of(m) - seen)
    return seen


@pytest.mark.unit
def test_the_dev_only_modules_are_exactly_those_nothing_installed_reaches():
    """They are left out of the wheel. Wiring one into the CLI, the MCP server, the web app or the guardrail
    makes it reachable: take it off setup.py's DEV_ONLY_MODULES, or every pip install breaks."""
    unreachable = set(_package_modules()) - _reachable_modules()
    assert set(_load_setup().DEV_ONLY_MODULES) == unreachable


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
    """Hugging Face's `datasets` installs site-packages/datasets/; that is not a checkout."""
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
def test_cli_plugin_dir_prints_an_ascii_short_path_for_a_non_ascii_install(monkeypatch, capsys):
    """Windows PowerShell 5.1 decodes `$(fusion plugin-dir)` with the OEM code page, mangling a non-ASCII
    path; its 8.3 short form survives any decoding."""
    import fusion_first._data
    import fusion_first.cli as cli

    short = r"C:\Users\JOS~1\AppData\Roaming\uv\tools\FUSION~1\MARKET~1"
    monkeypatch.setattr(fusion_first._data, "plugin_root",
                        lambda pkg_dir=None: pathlib.Path("C:/Users/José/AppData/Roaming/uv/tools/fusion-safety/m"))
    monkeypatch.setattr(cli, "_short_path", lambda p: short)

    assert cli.main(["plugin-dir"]) == 0
    assert capsys.readouterr().out.strip() == short


@pytest.mark.unit
def test_cli_plugin_dir_keeps_the_long_path_when_no_ascii_short_form_exists(monkeypatch, capsys):
    import fusion_first._data
    import fusion_first.cli as cli

    long = pathlib.Path("/home/josé/marketplace")
    monkeypatch.setattr(fusion_first._data, "plugin_root", lambda pkg_dir=None: long)
    monkeypatch.setattr(cli, "_short_path", lambda p: None)

    assert cli.main(["plugin-dir"]) == 0
    assert capsys.readouterr().out.strip() == str(long)


@pytest.mark.skipif(sys.platform != "win32", reason="8.3 short names are a Windows feature")
def test_short_path_of_a_real_non_ascii_folder_is_ascii_and_the_same_folder(tmp_path):
    from fusion_first.cli import _short_path

    folder = tmp_path / "Fusión"
    folder.mkdir()
    short = _short_path(folder)
    if short is None:
        pytest.skip("8.3 names are disabled on this volume")
    assert short.isascii() and pathlib.Path(short).samefile(folder)


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


@pytest.mark.unit
@pytest.mark.parametrize("argv", [["record", "--check", "direct_prompt_injection"],
                                  ["eval", "--check", "direct_prompt_injection", "--update-baseline"],
                                  ["guard-bench", "--update-baseline"]])
def test_commands_that_rewrite_the_corpora_refuse_in_a_pip_install(monkeypatch, capsys, argv):
    """In a pip install the corpora live inside site-packages (read-only for a system Python, replaced on
    upgrade), so the dev commands that rewrite them say where to run instead of writing there."""
    import fusion_first._data as data
    from fusion_first.cli import main

    bundled = pathlib.Path(data.__file__).resolve().parent / "_bundled"
    monkeypatch.setattr(data, "data_root", lambda pkg_dir=None: bundled)
    from fusion_first.model.replay import Cassette

    writes = []
    monkeypatch.setattr(pathlib.Path, "write_text", lambda self, *a, **k: writes.append(self))
    monkeypatch.setattr(Cassette, "save", lambda self, path: writes.append(path))

    assert main(argv) == 2
    assert writes == []
    assert "FUSION_DATA_DIR" in capsys.readouterr().err


@pytest.mark.unit
def test_the_pypi_page_renders_on_pypi():
    """PyPI renders neither Mermaid nor repository-relative links: the package page uses absolute links only."""
    import re

    text = (ROOT / "PYPI.md").read_text(encoding="utf-8")
    assert "```mermaid" not in text
    links = re.findall(r"\]\(([^)]+)\)", text)
    assert links and all(link.startswith("https://") for link in links)
