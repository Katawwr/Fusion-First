"""The release workflow publishes to PyPI by Trusted Publishing: a tag push builds, checks and uploads with a
short-lived OIDC identity, so no API token exists anywhere (owner, 2026-10-24)."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _load_check():
    spec = importlib.util.spec_from_file_location("release_tag_check", ROOT / "scripts" / "release_tag_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps_text(job) -> str:
    return "\n".join(str(s.get("run", "")) + " " + str(s.get("uses", "")) for s in job["steps"])


@pytest.mark.unit
def test_a_version_tag_push_is_the_only_trigger(wf):
    on = wf.get("on", wf.get(True))  # YAML 1.1 reads a bare `on` key as True
    assert set(on) == {"push"} and on["push"] == {"tags": ["v*"]}


@pytest.mark.unit
def test_publishing_uses_trusted_publishing_and_no_token(wf):
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text and "password" not in text.lower() and "TWINE_" not in text
    assert wf.get("permissions") == {"contents": "read"}
    publish = wf["jobs"]["publish"]
    assert publish["needs"] == "build"
    assert publish["permissions"] == {"id-token": "write"}
    assert publish["environment"]["name"] == "pypi"
    assert any(str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish@") for s in publish["steps"])


@pytest.mark.unit
def test_the_build_checks_the_tag_builds_the_web_app_first_and_smoke_tests_the_wheel(wf):
    steps = _steps_text(wf["jobs"]["build"])
    order = [steps.index(s) for s in ("release_tag_check.py", "frontend run build", "python -m build",
                                      "twine check", "pip install dist/")]
    assert order == sorted(order)
    assert "upload-artifact" in steps


@pytest.mark.unit
def test_the_tag_check_accepts_only_the_package_version():
    check = _load_check()
    version = check.package_version(ROOT)
    assert check.problems(ROOT, f"v{version}") == []
    assert check.problems(ROOT, f"refs/tags/v{version}") == []
    assert check.problems(ROOT, "v9.9.9")
    assert check.problems(ROOT, version)  # a tag needs the leading v
