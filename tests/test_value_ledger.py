"""The value ledger: of the real attacks found with the prompt as written, what the prompt fix removed,
what the runtime guardrail stopped (read from its registered measurement), and what neither caught.
Offline: seeded transcripts, real oracles."""

from __future__ import annotations

import pytest

from fusion_first.validate.experiments import build_items
from fusion_first.validate.transcripts import TranscriptRecord, TranscriptStore
from fusion_first.validate.value_ledger import value_ledger


def _say(store, item, arm, leak):
    pw = item.oracle["canaries"][0]
    store.append(TranscriptRecord(experiment="gandalf", item_id=item.item_id, model="m1", arm=arm,
                                  system_sha256="x", response=f"The password is {pw}." if leak else "No.",
                                  truncated=False))


@pytest.fixture
def ledger(tmp_path):
    store = TranscriptStore(tmp_path)
    a, b, c, d, e = build_items("gandalf", 5)
    #            as written, with fix
    for item, base, hard in ((a, True, False), (b, True, True), (c, False, True), (d, True, True), (e, False, False)):
        _say(store, item, "baseline", base)
        _say(store, item, "hardened", hard)
    guard = {"all": {"attacks": 3, "clean": 2, "over_blocked": 1},
             "not_stopped": [f"m1 {b.item_id}"]}  # the guard stopped a and d, missed b
    return value_ledger({"gandalf": [a, b, c, d, e]}, ["m1"], store, guard)


@pytest.mark.unit
def test_counts_each_layer_against_the_attacks_found(ledger):
    t = ledger["total"]
    assert (t["found"], t["fix_removed"], t["guard_stopped"], t["either"], t["neither"]) == (3, 1, 2, 2, 1)
    assert t["fix_caused"] == 1  # clean as written, attacked with the fix
    assert t["either_rate"]["point"] == pytest.approx(2 / 3, abs=1e-3)


@pytest.mark.unit
def test_reports_per_model(ledger):
    assert ledger["by_model"]["m1"]["found"] == 3


@pytest.mark.unit
def test_refuses_a_guard_measurement_that_does_not_match_the_attacks_found(tmp_path):
    store = TranscriptStore(tmp_path)
    (a,) = build_items("gandalf", 1)
    _say(store, a, "baseline", True)
    _say(store, a, "hardened", False)
    with pytest.raises(ValueError, match="attacks"):
        value_ledger({"gandalf": [a]}, ["m1"], store, {"all": {"attacks": 5}, "not_stopped": []})


@pytest.mark.integration
def test_committed_value_ledger_is_rederivable():
    """The published ledger re-derives exactly from committed transcripts, oracles and the registered
    guardrail measurement: no model involved."""
    import json
    import pathlib

    v1 = pathlib.Path(__file__).resolve().parents[1] / "evals/validation/v1"
    committed = json.loads((v1 / "value_ledger.json").read_text(encoding="utf-8"))
    guard = json.loads((v1 / "guard_on_transcripts.json").read_text(encoding="utf-8"))
    items = {e: build_items(e, 30) for e in ("injecagent", "gandalf")}
    fresh = value_ledger(items, committed["models"], TranscriptStore(v1 / "transcripts"), guard)
    for key in ("total", "by_model", "by_experiment"):
        assert json.loads(json.dumps(fresh[key])) == committed[key], key
