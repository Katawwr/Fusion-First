"""PREREG_local_grader.md: if the free local grader misses its registered bar, `fusion doctor` stops
recommending it by default AND the docs say why. While the committed evidence says it missed, every
user-facing line that names it must carry the reason (the policy floor), never a bare recommendation."""

from __future__ import annotations

import pathlib

import pytest

from fusion_first.validate.prereg import LOCAL_GRADER_EVIDENCE, local_grader_status

ROOT = pathlib.Path(__file__).resolve().parents[1]
USER_FACING = [
    "README.md",
    "integrations/README.md",
    "plugins/fusion/README.md",
    "plugins/fusion/skills/setup/SKILL.md",
    "plugins/fusion/skills/audit/SKILL.md",
    "frontend/src/content/integrations.json",
    "frontend/src/lib/targets.js",
]


@pytest.mark.unit
@pytest.mark.parametrize("model", sorted(LOCAL_GRADER_EVIDENCE))
def test_a_grader_below_its_registered_bar_is_never_recommended_without_the_reason(model):
    status = local_grader_status(model)
    if not (status["measured"] and not status["meets_floor"]):
        pytest.skip(f"{model} met its bar or is unmeasured")
    spec = f"ollama-prob:{model}"
    bare = [f"{rel}: {line.strip()}" for rel in USER_FACING
            for line in (ROOT / rel).read_text(encoding="utf-8").splitlines()
            if spec in line and "floor" not in line]
    assert not bare, "name the reason (below the policy floor, see TRUST_REPORT.md) or drop it:\n" + "\n".join(bare)
