"""evals/validation/v1/PREREG_LEDGER.md is generated from git history by scripts/prereg_ledger.py: it must equal a
fresh regeneration, every registration must precede the evidence it governs, and every evidence file that names a
registration must be governed by it."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prereg_ledger.py"
DETECTOR_PREREG = "evals/validation/v1/PREREG_detector_v1.md"


def _load_script():
    spec = importlib.util.spec_from_file_location("prereg_ledger_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LEDGER = _load_script()


def _full_history() -> bool:
    """The ledger reads commits: a checkout without git or a shallow clone (CI's default) cannot regenerate it."""
    try:
        out = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    return out == "false"


needs_history = pytest.mark.skipif(not _full_history(), reason="needs a full (non-shallow) git checkout")


@pytest.fixture(scope="module")
def rows():
    return LEDGER.ledger_rows(ROOT)


def _committed() -> str:
    return (ROOT / LEDGER.LEDGER).read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.mark.unit
@needs_history
def test_the_committed_ledger_matches_a_regeneration():
    assert _committed() == LEDGER.render(ROOT), "regenerate with: python scripts/prereg_ledger.py"


def _is_ancestor(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT).returncode == 0


@pytest.mark.unit
@needs_history
def test_every_registration_and_its_amendments_precede_the_evidence_it_governs(rows):
    for r in rows:
        for e in r["evidence"]:
            for c in [r, *r["later"]]:
                assert c["commit"] != e["commit"] and _is_ancestor(c["commit"], e["commit"]), (r["registration"], e)
                assert c["timestamp"] < e["timestamp"], (r["registration"], e["path"])


@pytest.mark.unit
@needs_history
def test_the_detector_registration_precedes_every_detector_evidence_file(rows):
    row = next(r for r in rows if r["registration"] == DETECTOR_PREREG)
    assert row["commit"].startswith("341c3d4") and row["later"] == []
    # Tracked files only: a working copy also holds gitignored local files (*.log) that no commit ever recorded.
    tracked = subprocess.run(["git", "ls-files", "--", "evals/validation/v1/detector"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout
    detector = set(tracked.splitlines())
    seal = "evals/validation/v1/detector/confirmatory.seal.json"  # committed with the registration itself
    assert {e["path"] for e in row["evidence"]} == detector - {seal}
    assert LEDGER.first_commit(ROOT, seal)["commit"] == row["commit"]
    assert all(e["timestamp"] > row["timestamp"] for e in row["evidence"])


@pytest.mark.unit
def test_every_registration_is_mapped_and_every_evidence_file_naming_one_is_governed_by_it():
    regs = LEDGER.registrations(ROOT)  # raises on a registration without a GOVERNS entry
    assert set(regs) == set(LEDGER.GOVERNS) and LEDGER.LEDGER not in regs
    assert all((ROOT / ev).is_file() for evs in LEDGER.GOVERNS.values() for ev in evs)
    for p in sorted((ROOT / "evals").rglob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        reg = data.get("preregistration") if isinstance(data, dict) else None
        rel = p.relative_to(ROOT).as_posix()
        if reg and not rel.endswith(".seal.json"):
            assert rel in LEDGER.GOVERNS.get(reg, []), f"{rel} names {reg} but the ledger does not list it"


@pytest.mark.unit
def test_the_ledger_hashes_are_the_registrations_committed_content():
    """No git needed: each row's sha256 is the registration's content as committed (LF line endings)."""
    hashes = dict(re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|", _committed(), re.MULTILINE))
    assert set(hashes) == set(LEDGER.registrations(ROOT))
    for rel, digest in hashes.items():
        content = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(content).hexdigest() == digest, f"{rel} changed since the ledger was generated"
    assert chr(0x2014) not in _committed()  # no em dashes
