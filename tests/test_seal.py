"""Held-out integrity: sealed blind splits, judge-prompt / remedy fingerprints, and the burn ledger.

The seal detects edited blind rows; the ledger declares a blind set burned after 3 distinct judge
prompts, because iterating a prompt against the same held-out set turns it into a dev set.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from fusion_first._data import data_root
from fusion_first.engine import fixes
from fusion_first.engine.fixes import Remedy
from fusion_first.judge.judge import build_system_prompt
from fusion_first.judge.rubric import REGISTRY, get_rubric
from fusion_first.schemas import Criterion
from fusion_first.validate.seal import (
    BlindLedger,
    compute_seal,
    judge_prompt_hash,
    load_seal,
    load_seal_meta,
    remedies_hash,
    row_hash,
    seal_digest,
    verify_seal,
    write_seal,
)


def _rows() -> list[dict]:
    return [
        {"id": "d1", "split": "dev", "q": "dev one", "is_issue": False},
        {"id": "b1", "split": "blind", "q": "blind one", "is_issue": True},
        {"id": "b2", "split": "blind", "q": "blind two", "is_issue": False},
        {"id": "b3", "split": "blind", "q": "café: unicode", "is_issue": True},
        {"id": "c1", "split": "canary", "q": "canary", "is_issue": True},
    ]


# ------------------------------------------------------------------ row_hash / compute_seal


@pytest.mark.unit
def test_row_hash_is_canonical_json_sha256():
    row = {"q": "café", "id": "x", "n": 1}
    canonical = '{"id":"x","n":1,"q":"café"}'
    assert row_hash(row) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.unit
def test_row_hash_ignores_key_order_but_not_values():
    a = {"id": "x", "q": "hello", "meta": {"b": 1, "a": 2}}
    b = {"meta": {"a": 2, "b": 1}, "q": "hello", "id": "x"}
    assert row_hash(a) == row_hash(b)
    assert row_hash(a) != row_hash({**a, "q": "hello "})
    assert row_hash(a) != row_hash({**a, "meta": {"a": 2, "b": True}})


@pytest.mark.unit
def test_compute_seal_covers_only_the_requested_split():
    rows = _rows()
    seal = compute_seal(rows)
    assert set(seal) == {"b1", "b2", "b3"}
    assert seal["b1"] == row_hash(rows[1])
    assert set(compute_seal(rows, split="canary")) == {"c1"}
    assert compute_seal(rows, split="nope") == {}


@pytest.mark.unit
def test_compute_seal_rejects_ambiguous_rows():
    with pytest.raises(ValueError, match="duplicate"):
        compute_seal([{"id": "b1", "split": "blind"}, {"id": "b1", "split": "blind", "x": 1}])
    with pytest.raises(ValueError, match="id"):
        compute_seal([{"split": "blind", "q": "no id"}])


# ------------------------------------------------------------------ write / load / verify


@pytest.mark.unit
def test_write_and_load_round_trip(tmp_path):
    seal = compute_seal(_rows())
    path = tmp_path / "seals" / "gold.blind.seal.json"
    write_seal(path, seal, {"dataset": "gold/direct_prompt_injection.v1", "split": "blind"})
    assert load_seal(path) == seal
    meta = load_seal_meta(path)
    assert meta["dataset"] == "gold/direct_prompt_injection.v1"
    assert meta["split"] == "blind"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["digest"] == seal_digest(seal)
    assert doc["n_rows"] == 3
    assert [p.name for p in path.parent.iterdir()] == ["gold.blind.seal.json"]  # atomic: no temp leftovers


@pytest.mark.unit
def test_load_seal_detects_an_edited_seal_file(tmp_path):
    path = tmp_path / "s.json"
    write_seal(path, compute_seal(_rows()), {})
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["rows"]["b1"] = "0" * 64  # someone "fixes" a hash to match an edited row
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        load_seal(path)


@pytest.mark.unit
def test_load_seal_rejects_garbage(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_seal(path)
    path.write_text(json.dumps({"rows": ["not", "a", "mapping"]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_seal(path)


@pytest.mark.unit
def test_seal_digest_is_order_independent_and_content_sensitive():
    seal = compute_seal(_rows())
    assert seal_digest(dict(reversed(list(seal.items())))) == seal_digest(seal)
    assert seal_digest({**seal, "b1": "0" * 64}) != seal_digest(seal)


@pytest.mark.unit
def test_verify_seal_intact():
    rows = _rows()
    assert verify_seal(rows, compute_seal(rows)) == {"changed": [], "missing": [], "added": []}


@pytest.mark.unit
def test_verify_seal_detects_tampering(tmp_path):
    rows = _rows()
    path = tmp_path / "s.json"
    write_seal(path, compute_seal(rows), {"split": "blind"})
    seal = load_seal(path)

    edited = [dict(r) for r in rows]
    edited[1]["is_issue"] = False  # relabel a blind row (b1)
    edited = [r for r in edited if r["id"] != "b2"]  # drop a blind row (b2)
    edited[2]["split"] = "dev"  # quietly move b3 out of the blind split
    edited.append({"id": "b9", "split": "blind", "q": "new"})  # smuggle in a new blind row
    edited[0]["q"] = "dev rows may change freely"

    assert verify_seal(edited, seal) == {
        "changed": ["b1"],
        "missing": ["b2", "b3"],
        "added": ["b9"],
    }


@pytest.mark.unit
def test_verify_seal_honours_split():
    rows = _rows()
    canary_seal = compute_seal(rows, split="canary")
    rows[4] = {**rows[4], "q": "edited"}
    assert verify_seal(rows, canary_seal, split="canary")["changed"] == ["c1"]


@pytest.mark.integration
def test_committed_gold_blind_splits_seal_and_verify():
    """The real gold sets: every blind split seals, verifies intact, and one edit is caught."""
    gold_dir = data_root() / "datasets" / "gold"
    files = sorted(gold_dir.glob("*.jsonl"))
    assert files, "no gold sets found"
    n_blind = 0
    for f in files:
        lines = f.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        seal = compute_seal(rows)
        n_blind += len(seal)
        assert verify_seal(rows, seal) == {"changed": [], "missing": [], "added": []}
        if seal:
            victim = next(r for r in rows if r.get("split") == "blind")
            tampered = [{**r, "tampered": True} if r is victim else r for r in rows]
            assert verify_seal(tampered, seal)["changed"] == [victim["id"]]
    assert n_blind > 0, "expected at least one committed blind row"


# ------------------------------------------------------------------ fingerprints


@pytest.mark.unit
def test_judge_prompt_hash_is_first_16_hex_of_the_system_prompt_sha256():
    rubric = get_rubric("direct_prompt_injection")
    expected = hashlib.sha256(build_system_prompt(rubric).encode("utf-8")).hexdigest()[:16]
    assert judge_prompt_hash(rubric) == expected
    assert judge_prompt_hash("direct_prompt_injection") == expected  # check name accepted too
    assert len(expected) == 16 and int(expected, 16) >= 0


@pytest.mark.unit
def test_judge_prompt_hash_distinguishes_rubrics_and_edits():
    hashes = {judge_prompt_hash(r) for r in REGISTRY.values()}
    assert len(hashes) == len(REGISTRY)
    rubric = get_rubric("excessive_agency")
    tweaked = rubric.model_copy(
        update={
            "criteria": [
                *rubric.criteria[:-1],
                Criterion(
                    id=rubric.criteria[-1].id,
                    question=rubric.criteria[-1].question + " Be strict.",
                    weight_severity=rubric.criteria[-1].weight_severity,
                ),
            ]
        }
    )
    assert judge_prompt_hash(tweaked) != judge_prompt_hash(rubric)


@pytest.mark.unit
def test_remedies_hash_is_stable_sha256():
    h = remedies_hash()
    assert h == remedies_hash()
    assert len(h) == 64 and int(h, 16) >= 0


@pytest.mark.unit
def test_remedies_hash_changes_when_any_remedy_text_changes(monkeypatch):
    base = remedies_hash()
    r = fixes.REMEDIES["data_exfiltration"]

    monkeypatch.setitem(
        fixes.REMEDIES,
        "data_exfiltration",
        Remedy(r.check, r.title, r.summary, [*r.rules[:-1], r.rules[-1] + "!"]),
    )
    rule_edit = remedies_hash()
    assert rule_edit != base

    monkeypatch.setitem(
        fixes.REMEDIES, "data_exfiltration", Remedy(r.check, r.title + " v2", r.summary, r.rules)
    )
    title_edit = remedies_hash()
    assert title_edit not in (base, rule_edit)

    monkeypatch.setitem(fixes.REMEDIES, "data_exfiltration", r)
    assert remedies_hash() == base
    monkeypatch.setitem(fixes.REMEDIES, "brand_new", Remedy("brand_new", "T", "S", ["rule"]))
    assert remedies_hash() != base


# ------------------------------------------------------------------ BlindLedger


@pytest.mark.unit
def test_ledger_starts_empty_without_creating_a_file(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = BlindLedger(path)
    assert ledger.uses("gold/dpi") == []
    assert ledger.burned("gold/dpi") is False
    assert not path.exists()


@pytest.mark.unit
def test_ledger_records_persist_across_instances(tmp_path):
    path = tmp_path / "nested" / "ledger.json"
    entry = BlindLedger(path).record_use("gold/dpi", "aaaa000011112222", note="first calibration")
    assert entry["dataset_id"] == "gold/dpi" and entry["judge_prompt_hash"] == "aaaa000011112222"
    uses = BlindLedger(path).uses("gold/dpi")
    assert len(uses) == 1
    assert uses[0]["note"] == "first calibration"
    assert uses[0]["at"]  # timestamped
    json.loads(path.read_text(encoding="utf-8"))  # plain JSON on disk
    assert [p.name for p in path.parent.iterdir()] == ["ledger.json"]  # atomic: no temp leftovers


@pytest.mark.unit
def test_ledger_burns_after_three_distinct_judge_prompts(tmp_path):
    ledger = BlindLedger(tmp_path / "ledger.json")
    ledger.record_use("gold/dpi", "h1")
    ledger.record_use("gold/dpi", "h2")
    assert not ledger.burned("gold/dpi")
    ledger.record_use("gold/dpi", "h3")
    assert ledger.burned("gold/dpi")
    assert not ledger.burned("gold/dpi", max_distinct_hashes=4)


@pytest.mark.unit
def test_rerunning_the_same_judge_prompt_does_not_burn(tmp_path):
    ledger = BlindLedger(tmp_path / "ledger.json")
    for _ in range(5):
        ledger.record_use("gold/dpi", "same-prompt")
    ledger.record_use("gold/dpi", "second-prompt")
    assert len(ledger.uses("gold/dpi")) == 6
    assert not ledger.burned("gold/dpi")


@pytest.mark.unit
def test_ledger_is_per_dataset(tmp_path):
    ledger = BlindLedger(tmp_path / "ledger.json")
    for h in ("h1", "h2", "h3"):
        ledger.record_use("gold/dpi", h)
    ledger.record_use("gold/exfil", "h1")
    assert ledger.burned("gold/dpi")
    assert not ledger.burned("gold/exfil")
    assert [u["judge_prompt_hash"] for u in ledger.uses("gold/exfil")] == ["h1"]


@pytest.mark.unit
def test_ledger_with_real_hashes_and_seal_digest_as_dataset_id(tmp_path):
    dataset_id = seal_digest(compute_seal(_rows()))
    ledger = BlindLedger(tmp_path / "ledger.json")
    for check in ("direct_prompt_injection", "excessive_agency", "data_exfiltration"):
        assert not ledger.burned(dataset_id)
        ledger.record_use(dataset_id, judge_prompt_hash(check))
    assert ledger.burned(dataset_id)


@pytest.mark.unit
def test_ledger_fails_closed_on_a_corrupt_file(tmp_path):
    """Silently starting a fresh ledger would 'un-burn' a burned blind set."""
    path = tmp_path / "ledger.json"
    path.write_text("{truncated", encoding="utf-8")
    ledger = BlindLedger(path)
    with pytest.raises(ValueError):
        ledger.burned("gold/dpi")
    with pytest.raises(ValueError):
        ledger.record_use("gold/dpi", "h1")
    assert path.read_text(encoding="utf-8") == "{truncated"  # never overwritten


@pytest.mark.unit
@pytest.mark.parametrize(("dataset_id", "prompt_hash"), [("", "h1"), ("gold/dpi", ""), ("  ", "h")])
def test_ledger_rejects_blank_ids(tmp_path, dataset_id, prompt_hash):
    with pytest.raises(ValueError):
        BlindLedger(tmp_path / "ledger.json").record_use(dataset_id, prompt_hash)


@pytest.mark.unit
def test_ledger_rejects_nonsense_threshold(tmp_path):
    with pytest.raises(ValueError):
        BlindLedger(tmp_path / "ledger.json").burned("gold/dpi", max_distinct_hashes=0)
