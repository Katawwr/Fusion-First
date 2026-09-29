"""The keyless install must not need (or even import) a metered provider SDK."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_core_dependencies_have_no_metered_sdk():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    core = " ".join(project["dependencies"]).lower()
    for sdk in ("anthropic", "openai", "scipy", "modal"):
        assert sdk not in core, f"{sdk} must be optional"
    assert set(project["optional-dependencies"]["api"]) >= {"anthropic>=0.40", "openai>=1.50"}
    assert project["scripts"]["fusion-mcp"] == "fusion_first.integrations.mcp_server:main"


@pytest.mark.unit
def test_keyless_surfaces_import_no_provider_sdk():
    code = (
        "import sys\n"
        "import fusion_first.cli, fusion_first.runs.cli, fusion_first.runs.service, fusion_first.backends.resolve\n"
        "import fusion_first.integrations.mcp_server, fusion_first.integrations.run_tools\n"
        "bad = sorted(m for m in ('anthropic', 'openai', 'scipy', 'modal') if m in sys.modules)\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
