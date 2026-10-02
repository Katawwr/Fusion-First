"""Replay the COMMITTED cassettes (`CASSETTE_DIR`, strict) through the real CLI paths, so drift from
the datasets is caught (`test_proof_pipeline.py` builds its cassettes in memory)."""

from __future__ import annotations

import pytest

from fusion_first.cli import main
from fusion_first.judge.rubric import checks_of_kind
from fusion_first.model.replay import Cassette
from fusion_first.recording import CASSETTE_DIR, build_full_cassette

SAFETY = checks_of_kind("safety")


@pytest.mark.integration
@pytest.mark.parametrize("check", SAFETY)
def test_prove_replays_committed_cassette(check, capsys):
    assert main(["prove", "--check", check]) == 0
    assert "Traceback" not in capsys.readouterr().out


@pytest.mark.integration
@pytest.mark.parametrize("check", SAFETY)
def test_eval_replays_committed_cassette(check):
    assert main(["eval", "--check", check]) == 0


@pytest.mark.integration
@pytest.mark.parametrize("check", SAFETY)
def test_committed_demo_cassettes_are_fresh(check):
    """Probes, gold rows, judge prompt or heuristic changed: run `fusion record --check all` and commit."""
    committed = Cassette.load(CASSETTE_DIR / f"{check}.v1.json")
    models = {e.get("model") for e in committed.entries.values()}
    if models != {"demo-heuristic-judge"}:
        pytest.skip(f"{check} cassette holds real recordings ({models}); freshness is by coverage")
    fresh = build_full_cassette(check)
    # Compare what replay actually serves (parsed responses), so additive optional response fields
    # don't read as staleness; any change to keys or verdict payloads still fails.
    assert set(committed.entries) == set(fresh.entries)
    assert all(committed.get(k) == fresh.get(k) for k in fresh.entries)


@pytest.mark.integration
def test_quality_eval_without_cassette_is_clean_usage_error(capsys, monkeypatch, tmp_path):
    import fusion_first.cli

    monkeypatch.setattr(fusion_first.cli, "CASSETTE_DIR", tmp_path)  # independent of local recordings
    code = main(["eval", "--check", "instruction_following"])
    out = capsys.readouterr().out
    assert code == 2
    assert "Traceback" not in out
    assert "record" in out


@pytest.mark.unit
def test_gold_hash_is_line_ending_independent(tmp_path, monkeypatch):
    from fusion_first import goldset

    lf = tmp_path / "x.v1.jsonl"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    monkeypatch.setattr(goldset, "GOLD_DIR", tmp_path)
    h_lf = goldset.gold_version_hash("x")
    lf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert goldset.gold_version_hash("x") == h_lf
