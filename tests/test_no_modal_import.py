"""Enforces the load-bearing architectural rule: the pure core (`fusion/`) must never
import `modal`. If it did, the offline uvicorn/pytest loop (the whole autonomous
test-and-improve workflow) would break the moment it touched that module.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

FUSION_ROOT = pathlib.Path(__file__).resolve().parent.parent / "fusion"


def _python_files() -> list[pathlib.Path]:
    return sorted(FUSION_ROOT.rglob("*.py"))


@pytest.mark.unit
def test_fusion_core_has_python_files():
    assert _python_files(), "fusion/ package has no modules yet"


@pytest.mark.unit
def test_no_module_imports_modal():
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name == "modal" or a.name.startswith("modal.") for a in node.names):
                    offenders.append(str(path))
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "modal" or node.module.startswith("modal.")):
                    offenders.append(str(path))
    assert not offenders, f"fusion/ must not import modal; offenders: {offenders}"
