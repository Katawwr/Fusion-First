"""Every proof-like number in docs and marketing must be backed by committed, non-demo evidence."""

from __future__ import annotations

import json

import pytest

from fusion_first.validate.claims import (
    check_claim,
    load_registry,
    repo_root,
    unregistered_proof_strings,
)

ROOT = repo_root()
REGISTRY = load_registry()


@pytest.mark.unit
@pytest.mark.parametrize("claim", REGISTRY.claims, ids=lambda c: c.get("id", "?"))
def test_registered_claim_is_backed_by_evidence(claim):
    problems = check_claim(claim, ROOT)
    assert not problems, [p.message for p in problems]


@pytest.mark.unit
def test_no_unregistered_proof_numbers_in_docs_or_marketing():
    stray = unregistered_proof_strings(REGISTRY, ROOT)
    assert not stray, "register these in evals/claims.yaml (with evidence) or remove them:\n" + "\n".join(
        f"  {f}:{n}: {line}" for f, n, line in stray
    )


@pytest.mark.unit
def test_claim_checker_rejects_demo_and_mismatched_evidence(tmp_path):
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"demonstration": True, "f1": 0.75, "n": 10}), encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("Judge F1 1.00 on the blind set", encoding="utf-8")
    claim = {
        "id": "x", "text": "F1 1.00", "files": ["doc.md"], "evidence": "ev.json",
        "metrics": {"f1": 1.0}, "n_path": "n", "min_n": 30,
    }
    msgs = " | ".join(p.message for p in check_claim(claim, tmp_path))
    assert "demonstration" in msgs
    assert "claimed 1.0" in msgs
    assert "below min_n" in msgs


@pytest.mark.unit
def test_scanner_catches_classic_unbacked_claims(tmp_path):
    from fusion_first.validate.claims import PROOF_PATTERNS

    for line in [
        'stat: "62% injection · 67% data-leak",',
        "Graded by an examiner that scores F1&nbsp;1.00",
        "frontier models resist (verified: Haiku 0%)",
        "kappa=1.00 on blind",
        "open-weight models don't (verified: llama3.2:1b 62% on injection)",
    ]:
        assert any(p.search(line) for p in PROOF_PATTERNS), line
    for benign in ['width: "100%",', 'transform: "translateX(-50%)",', "95% confidence interval"]:
        assert not any(p.search(benign) for p in PROOF_PATTERNS), benign


@pytest.mark.unit
def test_missing_demonstration_flag_is_treated_as_demo(tmp_path):
    (tmp_path / "ev.json").write_text(json.dumps({"f1": 0.9, "n": 100}), encoding="utf-8")
    (tmp_path / "doc.md").write_text("F1 0.90", encoding="utf-8")
    claim = {"id": "x", "text": "F1 0.90", "files": ["doc.md"], "evidence": "ev.json", "metrics": {"f1": 0.9}}
    assert any("demonstration" in p.message for p in check_claim(claim, tmp_path))


@pytest.mark.unit
def test_per_metric_denominator_is_enforced(tmp_path):
    (tmp_path / "ev.json").write_text(
        json.dumps({"demonstration": False, "recall": 1.0, "malicious": 4, "n": 400}), encoding="utf-8"
    )
    (tmp_path / "doc.md").write_text("recall 100%", encoding="utf-8")
    claim = {
        "id": "x", "text": "recall 100%", "files": ["doc.md"], "evidence": "ev.json",
        "metrics": {"recall": {"value": 1.0, "n_path": "malicious", "min_n": 30}},
    }
    assert any("below min_n" in p.message for p in check_claim(claim, tmp_path))


@pytest.mark.unit
def test_registered_claim_cannot_shelter_a_second_number(tmp_path):
    from fusion_first.validate.claims import Registry, unregistered_proof_strings

    (tmp_path / "README.md").write_text(
        "Guard: 100% recall / 0% over-block, and llama fails 62% of injection attacks.\n",
        encoding="utf-8",
    )
    reg = Registry(claims=[{"text": "100% recall / 0% over-block", "files": ["README.md"]}])
    assert unregistered_proof_strings(reg, tmp_path)


@pytest.mark.unit
def test_scanner_catches_numbers_split_across_lines(tmp_path):
    from fusion_first.validate.claims import Registry, unregistered_proof_strings

    (tmp_path / "README.md").write_text("our judge scores an F1 of\n0.97 on the blind set\n", encoding="utf-8")
    assert unregistered_proof_strings(Registry(), tmp_path)


@pytest.mark.unit
def test_scanner_catches_more_claim_shapes():
    from fusion_first.validate.claims import PROOF_PATTERNS

    for line in ["recall 100%", "accuracy of 92%", "issue rate 72% -> 11%", "5 percent got through",
                 "kappa of 0.8", "precision: .95"]:
        assert any(p.search(line) for p in PROOF_PATTERNS), line


@pytest.mark.unit
def test_scanner_skips_test_fixtures_but_not_components(tmp_path):
    from fusion_first.validate.claims import scanned_files

    lib = tmp_path / "frontend/src/lib"
    lib.mkdir(parents=True)
    (lib / "trust.js").write_text("x", encoding="utf-8")
    (lib / "trust.test.js").write_text("x", encoding="utf-8")
    (lib / "Card.spec.jsx").write_text("x", encoding="utf-8")
    names = {p.name for p in scanned_files(tmp_path)}
    assert "trust.js" in names and "trust.test.js" not in names and "Card.spec.jsx" not in names


@pytest.mark.unit
def test_docs_folder_is_scanned_for_proof_numbers(tmp_path):
    """docs/*.md is reviewer-facing copy: an unregistered rate there must fail like one in the README."""
    from fusion_first.validate.claims import scanned_files

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text("the guard stopped 97% of attacks", encoding="utf-8")
    assert tmp_path / "docs" / "ARCHITECTURE.md" in scanned_files(tmp_path)
    stray = unregistered_proof_strings(load_registry(), tmp_path)
    assert [f for f, _, _ in stray] == ["docs/ARCHITECTURE.md"]
