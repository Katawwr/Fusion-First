"""The judge ledger: measured accuracy per judge backend, and the qualification gate on it."""

from __future__ import annotations

import pytest

from fusion.judge.ledger import (
    LedgerEntry,
    Qualification,
    judge_fingerprint,
    ledger_accuracy_provider,
    load_entry,
    qualify,
    save_entry,
)
from fusion.stats.metrics import accuracy_result

CHECK = "direct_prompt_injection"


def _acc(tp, fp, tn, fn, n_unscored=0):
    y = [True] * tp + [False] * fp + [False] * tn + [True] * fn
    p = [True] * tp + [True] * fp + [False] * tn + [False] * fn
    return accuracy_result(y, p, label_source="oracle").model_copy(update={"n_unscored": n_unscored})


def _entry(acc, model="claude-sonnet-5", backend="claude_cli"):
    return LedgerEntry(
        backend=backend, model_id=model, check=CHECK, fingerprint=judge_fingerprint(backend, model, CHECK),
        gold_version="g1", split="blind", accuracy=acc.model_dump(), measured_at="2026-09-26",
        evidence="cassettes/validation/v1/x.json", label_tier="oracle",
    )


@pytest.mark.unit
def test_qualification_levels():
    assert qualify(None)[0] == Qualification.UNMEASURED
    assert qualify(_acc(48, 1, 49, 2))[0] == Qualification.QUALIFIED
    status, reasons = qualify(_acc(4, 0, 5, 1))  # accurate but tiny n -> wide interval
    assert status == Qualification.PROVISIONAL and "lower bound" in reasons[0]
    assert qualify(_acc(2, 6, 4, 8))[0] == Qualification.UNQUALIFIED
    assert qualify(_acc(40, 1, 40, 1, n_unscored=30))[0] == Qualification.UNQUALIFIED


@pytest.mark.unit
def test_save_and_load_roundtrip(tmp_path):
    entry = _entry(_acc(40, 2, 40, 3))
    save_entry(entry, tmp_path)
    got = load_entry("claude_cli", "claude-sonnet-5", CHECK, roots=[tmp_path])
    assert got is not None and got.result.tp == 40


@pytest.mark.unit
def test_stale_fingerprint_is_ignored(tmp_path):
    entry = _entry(_acc(40, 2, 40, 3))
    entry.fingerprint = "0000000000000000"  # measured with an older rubric/judge
    save_entry(entry, tmp_path)
    assert load_entry("claude_cli", "claude-sonnet-5", CHECK, roots=[tmp_path]) is None


@pytest.mark.unit
def test_fingerprint_depends_on_backend_and_model():
    a = judge_fingerprint("claude_cli", "claude-sonnet-5", CHECK)
    assert a != judge_fingerprint("ollama_prob", "qwen2.5:7b", CHECK)
    assert a != judge_fingerprint("claude_cli", "claude-opus-4-8", CHECK)
    assert a == judge_fingerprint("claude_cli", "claude-sonnet-5", CHECK)


@pytest.mark.unit
async def test_provider_supplies_ledger_accuracy_or_a_note(tmp_path):
    save_entry(_entry(_acc(4, 0, 5, 1)), tmp_path)
    provider = ledger_accuracy_provider("claude_cli", "claude-sonnet-5", roots=[tmp_path])
    acc, gold, note, source = await provider(CHECK, "claude-sonnet-5")
    assert acc is not None and gold == "g1"
    assert note.startswith("PROVISIONAL") and source.startswith("ledger (oracle")
    missing = ledger_accuracy_provider("ollama_prob", "qwen2.5:7b", roots=[tmp_path])
    acc2, _, note2, _ = await missing(CHECK, "qwen2.5:7b")
    assert acc2 is None and "fusion judge qualify" in note2
