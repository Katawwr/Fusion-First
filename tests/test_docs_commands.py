"""Every `fusion …` command shown in the docs must parse with the real CLI parser (docs can't drift)."""

from __future__ import annotations

import pathlib
import re
import shlex

import pytest

from fusion.cli import build_parser

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ["README.md", "CLAUDE.md", "plugins/fusion/README.md", "plugins/fusion-guard/README.md"]


def _commands():
    for doc in DOCS:
        text = (ROOT / doc).read_text(encoding="utf-8")
        for block in re.findall(r"```(?:bash|sh)?\n(.*?)```", text, re.S):
            for line in block.splitlines():
                line = line.split(" #")[0].strip()
                for part in re.split(r"&&|;|\|", line):
                    part = re.sub(r"\s[<>]\s*\S+", "", part).strip()
                    for prefix in ("python -m fusion.cli ", "fusion "):
                        if part.startswith(prefix):
                            yield doc, part[len(prefix):]


def _content_commands():
    """The /use page renders frontend/src/content/integrations.json — its commands must parse too."""
    import json

    data = json.loads((ROOT / "frontend/src/content/integrations.json").read_text(encoding="utf-8"))
    for section in data["sections"]:
        for step in section["steps"]:
            if step["lang"] != "bash":
                continue
            for line in step["code"].splitlines():
                if line.startswith("fusion "):
                    yield "integrations.json", line[len("fusion "):]


def _example_commands():
    """Commands inside the shipped CI / pre-commit examples."""
    for rel in ("integrations/examples/github-action.yml", "integrations/examples/pre-commit-config.yaml"):
        for line in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            line = line.split(" #")[0].strip().lstrip("#").strip()
            if line.startswith("fusion ") and not line.startswith("fusion-"):
                yield rel, line[len("fusion "):]


def _app_hint_commands():
    """CLI commands the web app shows outside /use (the Quality panel's hint when no live model runs)."""
    rel = "frontend/src/components/scan/QualityPanel.jsx"
    for code in re.findall(r"<code>(.*?)</code>", (ROOT / rel).read_text(encoding="utf-8"), re.S):
        line = " ".join(code.split())
        if line.startswith("fusion "):
            yield rel, line[len("fusion "):]


CASES = list(_commands()) + list(_content_commands()) + list(_example_commands()) + list(_app_hint_commands())


@pytest.mark.unit
def test_the_quality_hint_grades_the_users_own_prompt():
    """Without --prompt, `fusion measure --stages quality` grades "You are a helpful assistant.", not the
    agent the user pasted."""
    parsed = [build_parser().parse_args(shlex.split(a)) for _, a in _app_hint_commands()]
    graders = [ns for ns in parsed if hasattr(ns, "prompt")]
    assert graders and all(ns.prompt for ns in graders)


@pytest.mark.unit
def test_docs_show_fusion_commands():
    assert len(CASES) >= 10


@pytest.mark.unit
@pytest.mark.parametrize("doc, argv", CASES, ids=[f"{d}:{a[:40]}" for d, a in CASES])
def test_documented_command_parses(doc, argv):
    try:
        build_parser().parse_args(shlex.split(argv))
    except SystemExit as e:  # argparse exits on error
        pytest.fail(f"{doc}: `fusion {argv}` does not parse (exit {e.code})")
