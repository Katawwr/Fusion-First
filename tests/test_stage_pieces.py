"""The development pilot for the stage's markup cost, dilution and hidden text (`scripts/stage_pieces.py`).
Offline: stand-in replies only, and every path it could write points into tmp_path."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from fusion_first.guardrail import stages
from fusion_first.guardrail.stages import LlamaGuard


def _script():
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "stage_pieces.py"
    spec = importlib.util.spec_from_file_location("stage_pieces_script", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Ollama:
    def __init__(self):
        self.asked = []

    def __call__(self, path: str, payload: dict | None = None) -> dict:
        if path == "/api/tags":
            return {"models": [{"name": stages.LLAMA_GUARD_MODEL, "digest": "d" * 12}]}
        if path == "/api/ps":
            return {"models": []}
        self.asked.append(payload["prompt"])
        return {"response": "unsafe\nS2" if "(h2)" in payload["prompt"] else "safe"}


@pytest.mark.unit
def test_brackets_are_swapped_only_inside_the_block():
    script, stage, text = _script(), LlamaGuard(), "a <b> c"
    before = stage.prompt(text)
    with script.brackets("square"):
        assert "a [b] c" in stage.prompt(text)
    with script.brackets("space"):
        assert "a  b  c" in stage.prompt(text)
    assert stage.prompt(text) == before and "a (b) c" in before


@pytest.mark.integration
def test_the_pilot_asks_each_prompt_once_resumes_and_tabulates(tmp_path, monkeypatch, capsys):
    script = _script()
    monkeypatch.setattr(script, "PILOT", tmp_path / "pilot.jsonl")
    monkeypatch.setattr(script, "N_SENTENCES", 5)
    units = script.units()
    assert {u["group"] for u in units} == {"markup/paren", "markup/square", "markup/space", "ifeval/whole",
                                           "ifeval/sentences"}
    assert sum(u["group"] == "markup/square" for u in units) == 400 and sum(u["group"] == "ifeval/whole" for u in units) == 5
    assert any(len(u["prompts"]) > 1 for u in units if u["group"] == "ifeval/sentences")
    ollama = _Ollama()
    assert script.main(["pilot"], transport=ollama) == 0
    distinct = {p for u in units for p in u["prompts"]}
    assert len(ollama.asked) == len(set(ollama.asked)) == len(distinct)
    out = capsys.readouterr().out
    assert "markup/paren       safe   flagged 200 of 200" in out and "markup/square      safe   flagged   0 of 200" in out
    assert script.main(["pilot"], transport=ollama) == 0 and len(ollama.asked) == len(distinct)  # resumed


@pytest.mark.unit
def test_line_breaks_are_kept_only_inside_the_block():
    script, stage, text = _script(), LlamaGuard(), "a\n\n<b>\r\nc"
    before = stage.prompt(text)
    with script.rendering("newline", "paren"):
        assert "a\n(b)\nc" in stage.prompt(text)
    with script.rendering("slash", "paren"):
        assert "a / (b) / c" in stage.prompt(text)
    with script.rendering("flat", "angle"):
        assert "a  <b> c" in stage.prompt(text)
    assert stage.prompt(text) == before and "a  (b) c" in before


@pytest.mark.integration
def test_the_follow_up_pilot_reuses_the_studys_replies_and_tabulates(tmp_path, monkeypatch, capsys):
    script = _script()
    monkeypatch.setattr(script, "PILOT", tmp_path / "pilot.jsonl")
    assert not any("forged" in u["group"] for u in script.units2())
    units = script.units2(("slash",))
    assert sum(u["group"] == "markup/newline-paren" for u in units) == 400
    assert sum(u["group"] == "forged_turn/slash" for u in units) == 200
    assert not any(u["group"].endswith(("/flat", "/newline")) for u in units)
    known = {r["prompt_sha256"] for r in script._study()._jsonl(script.STUDY_RAW)}
    todo = {p for u in units for p in u["prompts"] if script._sha(p) not in known}
    ollama = _Ollama()
    assert script.main(["pilot2", "--structure", "slash"], transport=ollama) == 0
    assert len(ollama.asked) == len(set(ollama.asked)) == len(todo)
    assert "markup/flat-angle" in capsys.readouterr().out
    assert script.main(["pilot2", "--structure", "slash"], transport=ollama) == 0
    assert len(ollama.asked) == len(todo)  # resumed
