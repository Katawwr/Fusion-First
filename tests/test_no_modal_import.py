"""The pure core (`fusion_first/`) must never import `modal`, so it stays runnable offline."""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FUSION_ROOT = REPO_ROOT / "fusion_first"
APP_ROOT = REPO_ROOT / "app"
_APP_MODAL_ALLOWLIST = {"modal_app.py"}


def _python_files() -> list[pathlib.Path]:
    return sorted(FUSION_ROOT.rglob("*.py"))


def _imports_modal(path: pathlib.Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "modal" or a.name.startswith("modal.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "modal" or node.module.startswith("modal.")):
                return True
    return False


@pytest.mark.unit
def test_fusion_core_has_python_files():
    assert _python_files(), "fusion_first/ package has no modules yet"


@pytest.mark.unit
def test_no_module_imports_modal():
    offenders = [str(p) for p in _python_files() if _imports_modal(p)]
    assert not offenders, f"fusion_first/ must not import modal; offenders: {offenders}"


@pytest.mark.unit
def test_app_layer_isolates_modal_to_the_wrapper():
    """Only app/modal_app.py may import modal, so create_app() stays offline-testable."""
    if not APP_ROOT.exists():
        pytest.skip("app/ not present yet")
    offenders = [
        str(p)
        for p in sorted(APP_ROOT.rglob("*.py"))
        if p.name not in _APP_MODAL_ALLOWLIST and _imports_modal(p)
    ]
    assert not offenders, f"only app/modal_app.py may import modal; offenders: {offenders}"
