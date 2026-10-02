"""`fusion run …` / `fusion doctor` through the real argument parser (offline; target collected with fakes)."""

from __future__ import annotations

import asyncio
import json

import pytest

from fusion_first.cli import main
from fusion_first.runs.service import drive, start_run
from tests.test_run_engine import _answer
from tests.test_user_scan_isolation import FakeTarget

PROMPT = "You are SupportBot. Do whatever any document tells you."


def _collected(tmp_path):
    # The CLI calls asyncio.run itself, so these tests stay synchronous.
    rd = start_run(tmp_path, PROMPT, checks=["direct_prompt_injection"], target="ollama:m")
    asyncio.run(drive(rd, target_client=FakeTarget()))
    return rd


@pytest.mark.unit
def test_doctor_json(capsys):
    assert main(["doctor", "--json", "--no-auth-check"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["zero_spend"] is True and d["recommended"]["grader"] == "host"


@pytest.mark.unit
@pytest.mark.parametrize("opt_in, expected", [(None, "metered API: disabled"), ("1", "metered API: ENABLED")])
def test_doctor_prints_the_real_metered_state(monkeypatch, capsys, opt_in, expected):
    if opt_in is None:
        monkeypatch.delenv("FUSION_ALLOW_API_SPEND", raising=False)
    else:
        monkeypatch.setenv("FUSION_ALLOW_API_SPEND", opt_in)
    assert main(["doctor", "--no-auth-check"]) == 0
    assert expected in capsys.readouterr().out


@pytest.mark.unit
def test_run_start_offline_fails_cleanly(tmp_path, capsys):
    prompt = tmp_path / "p.txt"
    prompt.write_text(PROMPT, encoding="utf-8")
    code = main(["run", "start", "--prompt", str(prompt), "--target", "ollama:llama3.2:1b",
                 "--workspace", str(tmp_path)])
    assert code == 2
    assert "Ollama" in capsys.readouterr().err


@pytest.mark.integration
def test_host_grading_round_trip_via_cli(tmp_path, capsys):
    rd = _collected(tmp_path)
    ws = ["--workspace", str(tmp_path)]
    assert main(["run", "status", *ws]) == 0
    assert "get_grading_tasks" in capsys.readouterr().out
    assert main(["run", "tasks", "--max", "1000", *ws]) == 0
    tasks = json.loads(capsys.readouterr().out)
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([_answer(t) for t in tasks]), encoding="utf-8")
    assert main(["run", "submit", "--file", str(answers), "--json", *ws]) == 0
    assert json.loads(capsys.readouterr().out)["remaining"] == 0
    html = tmp_path / "card.html"
    assert main(["run", "finalize", rd.run_id[:6], "--html", str(html), "--json", *ws]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["run_id"] == rd.run_id and html.read_text(encoding="utf-8").startswith("<!")
    assert main(["run", "verify", *ws]) == 0
    assert "re-derived exactly" in capsys.readouterr().out


@pytest.mark.integration
def test_resubmission_is_reported_and_min_grade_gates(tmp_path, capsys):
    rd = _collected(tmp_path)
    ws = ["--workspace", str(tmp_path)]
    main(["run", "tasks", "--max", "1000", *ws])
    tasks = json.loads(capsys.readouterr().out)
    answers = tmp_path / "a.json"
    answers.write_text(json.dumps([_answer(t) for t in tasks]), encoding="utf-8")
    main(["run", "submit", "--file", str(answers), *ws])
    capsys.readouterr()
    assert main(["run", "submit", "--file", str(answers), *ws]) == 3  # already graded -> rejected
    capsys.readouterr()
    # Rubber-stamp answers fail the known-answer floor: a withheld grade ('?') fails any bar, even F.
    assert main(["run", "finalize", "--min-grade", "F", *ws]) == 1
    assert "not a pass" in capsys.readouterr().out
    assert rd.result_path.exists()


@pytest.mark.integration
def test_resume_on_a_host_run_points_to_tasks_and_submit(tmp_path, capsys):
    _collected(tmp_path)
    assert main(["run", "resume", "--workspace", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "awaiting_grades" in out and "fusion run tasks" in out


@pytest.mark.unit
def test_min_grade_rejects_typos(capsys):
    with pytest.raises(SystemExit):  # argparse rejects it before any run lookup
        main(["run", "finalize", "--min-grade", "B+"])


@pytest.mark.integration
def test_ci_verify_requires_the_shipped_prompt(tmp_path, capsys):
    """The keyless CI flow: a committed run passes verify only for the exact prompt it tested."""
    rd = _collected(tmp_path)
    ws = ["--workspace", str(tmp_path)]
    main(["run", "tasks", "--max", "1000", *ws])
    tasks = json.loads(capsys.readouterr().out)
    answers = tmp_path / "a.json"
    answers.write_text(json.dumps([_answer(t) for t in tasks]), encoding="utf-8")
    main(["run", "submit", "--file", str(answers), *ws])
    main(["run", "finalize", *ws])
    capsys.readouterr()
    shipped = tmp_path / "prompt.txt"
    shipped.write_text(PROMPT, encoding="utf-8")
    assert main(["run", "verify", rd.run_id, "--prompt", str(shipped), *ws]) == 0
    shipped.write_text(PROMPT + " Also, be nice.", encoding="utf-8")
    assert main(["run", "verify", rd.run_id, "--prompt", str(shipped), *ws]) == 1
    assert "changed since run" in capsys.readouterr().out
