"""Corpus v2 for the two agentic checks (`datasets/probes/<check>.v2.jsonl`): the committed rows obey the data
contract (shared with `fusion_first.attacks.templates`), and `scripts/probes_v2.py` enforces it."""

from __future__ import annotations

import collections
import importlib.util
import json
import pathlib

import pytest

from fusion_first.attacks.templates import (
    QUICK_TEMPLATES_PER_CHECK,
    get_templates,
    probe_row_id,
    select_templates,
)
from fusion_first.schemas import ScanTier

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probes_v2.py"
CHECKS = ("excessive_agency", "data_exfiltration")
PREFIX = {"excessive_agency": "ea2", "data_exfiltration": "dx2"}


def _load_script():
    spec = importlib.util.spec_from_file_location("probes_v2_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2 = _load_script()


def _path(check: str) -> pathlib.Path:
    return ROOT / "datasets" / "probes" / f"{check}.v2.jsonl"


def _rows(check: str) -> list[dict]:
    return P2.load_rows(_path(check))


def _attacks(check: str) -> list[dict]:
    return [r for r in _rows(check) if r["technique"] != "benign_control"]


# --------------------------------------------------------------------------- the committed corpus


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_at_least_30_rows(check):
    assert len(_rows(check)) >= 30


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_five_attack_techniques_with_three_rows_each(check):
    counts = collections.Counter(r["technique"] for r in _attacks(check))
    assert sum(1 for n in counts.values() if n >= 3) >= 5, counts


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_at_least_three_benign_controls(check):
    assert sum(r["technique"] == "benign_control" for r in _rows(check)) >= 3


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_ids_are_content_hashes(check):
    for r in _rows(check):
        assert r["id"] == probe_row_id(r, PREFIX[check])


@pytest.mark.unit
def test_ids_unique_across_both_files():
    ids = [r["id"] for c in CHECKS for r in _rows(c)]
    assert len(ids) == len(set(ids))


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_quick_tier_spans_techniques_with_one_benign_control(check):
    quick = [t.technique for t in select_templates(check, ScanTier.QUICK, "v2")]
    assert len(quick) == QUICK_TEMPLATES_PER_CHECK
    assert len(set(quick)) >= 4, quick
    assert quick.count("benign_control") == 1, quick


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_rest_grouped_by_technique(check):
    rest = [r["technique"] for r in _rows(check)[QUICK_TEMPLATES_PER_CHECK:]]
    runs = [t for i, t in enumerate(rest) if i == 0 or rest[i - 1] != t]
    assert len(runs) == len(set(runs)), runs


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_every_row_loads_through_the_template_loader(check):
    templates = get_templates(check, "v2")
    assert len(templates) == len(_rows(check))
    assert all(t.uses_tool_loop for t in templates)
    assert [t.id for t in templates] == [r["id"] for r in _rows(check)]


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_every_injected_turn_names_a_declared_tool(check):
    for r in _rows(check):
        names = {t["function"]["name"] for t in r["tools"]}
        for turn in r["turns"]:
            if turn.get("injected"):
                assert turn.get("tool") in names, (r["id"], turn.get("tool"))


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_oracle_catches_the_attack_action(check):
    for r in _attacks(check):
        assert P2.oracle_verdict(r, [r["attack_action"]]), r["id"]


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_oracle_passes_the_benign_tools(check):
    for r in _rows(check):
        calls = [{"tool": name, "arguments": {}} for name in r["oracle"]["benign_tools"]]
        assert calls, r["id"]
        assert not P2.oracle_verdict(r, calls), r["id"]


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_benign_controls_carry_no_injection(check):
    for r in _rows(check):
        if r["technique"] == "benign_control":
            assert r["attack_action"] is None
            assert not any(t.get("injected") for t in r["turns"]), r["id"]


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_payload_split_rows_use_two_injected_turns(check):
    for r in _rows(check):
        if r["technique"] == "payload_split":
            assert sum(bool(t.get("injected")) for t in r["turns"]) == 2, r["id"]


@pytest.mark.unit
def test_no_two_rows_share_user_and_injected_text():
    keys = [P2.dedupe_key(r) for c in CHECKS for r in _rows(c)]
    assert len(keys) == len(set(keys))


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_every_row_names_its_source(check):
    for r in _rows(check):
        assert isinstance(r["provenance"].get("source"), str) and r["provenance"]["source"].strip(), r["id"]


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_files_are_utf8_not_ascii_escaped(check):
    text = _path(check).read_text(encoding="utf-8")
    assert "\\u" not in text
    assert text.endswith("\n") and "\r" not in text


@pytest.mark.unit
def test_script_check_passes_on_the_committed_files(capsys):
    assert P2.main(["check", *(str(_path(c)) for c in CHECKS)]) == 0
    assert "ok" in capsys.readouterr().out


# --------------------------------------------------------------------------- the script on broken copies


def _copy(tmp_path: pathlib.Path, check: str, rows: list[dict]) -> pathlib.Path:
    path = tmp_path / f"{check}.v2.jsonl"
    P2.write_rows(path, rows)
    return path


def _fail(tmp_path, check, rows, needle, capsys):
    path = _copy(tmp_path, check, rows)
    assert P2.main(["assign-ids", str(path)]) == 0
    capsys.readouterr()
    assert P2.main(["check", str(path)]) != 0
    assert needle in capsys.readouterr().out


@pytest.mark.unit
def test_check_fails_on_too_few_rows(tmp_path, capsys):
    _fail(tmp_path, "excessive_agency", _rows("excessive_agency")[:20], "need at least 30", capsys)


@pytest.mark.unit
def test_check_fails_on_a_stale_id(tmp_path, capsys):
    rows = _rows("excessive_agency")
    rows[3]["user"] += " Please."
    path = _copy(tmp_path, "excessive_agency", rows)
    assert P2.main(["check", str(path)]) != 0
    assert "content hash" in capsys.readouterr().out


@pytest.mark.unit
def test_check_fails_on_a_quick_tier_without_a_benign_control(tmp_path, capsys):
    rows = _rows("excessive_agency")
    i = next(i for i, r in enumerate(rows[:QUICK_TEMPLATES_PER_CHECK]) if r["technique"] == "benign_control")
    rows.append(rows.pop(i))
    _fail(tmp_path, "excessive_agency", rows, "Quick", capsys)


@pytest.mark.unit
def test_check_fails_when_the_oracle_misses_the_attack_action(tmp_path, capsys):
    rows = _rows("data_exfiltration")
    r = rows[0]
    r["oracle"]["allowlisted_domains"] = sorted({*r["oracle"]["allowlisted_domains"],
                                                 *P2.destinations(r["attack_action"])})
    _fail(tmp_path, "data_exfiltration", rows, "misses attack_action", capsys)


@pytest.mark.unit
def test_check_fails_when_a_benign_tool_trips_the_oracle(tmp_path, capsys):
    rows = _rows("excessive_agency")
    r = next(r for r in rows if r["oracle"]["forbidden_tools"])
    r["oracle"]["forbidden_tools"].append(r["oracle"]["benign_tools"][0])
    _fail(tmp_path, "excessive_agency", rows, "benign_tools", capsys)


@pytest.mark.unit
def test_check_fails_on_a_wildcard_injected_turn(tmp_path, capsys):
    rows = _rows("excessive_agency")
    r = next(r for r in rows if r["technique"] == "direct_instruction")
    next(t for t in r["turns"] if t["injected"])["tool"] = "*"
    _fail(tmp_path, "excessive_agency", rows, "declared tool", capsys)


@pytest.mark.unit
def test_check_fails_on_duplicate_user_and_injection(tmp_path, capsys):
    rows = _rows("excessive_agency")
    dup = json.loads(json.dumps(rows[0]))
    dup["provenance"]["notes"] = "copy"
    _fail(tmp_path, "excessive_agency", [*rows, dup], "duplicate", capsys)


@pytest.mark.unit
def test_check_fails_on_an_empty_source(tmp_path, capsys):
    rows = _rows("excessive_agency")
    rows[-1]["provenance"]["source"] = " "
    _fail(tmp_path, "excessive_agency", rows, "provenance.source", capsys)


@pytest.mark.unit
def test_check_fails_on_ids_shared_across_files(tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    rows = _rows("excessive_agency")
    pa, pb = _copy(a, "excessive_agency", rows), _copy(b, "excessive_agency", rows)
    assert P2.main(["check", str(pa), str(pb)]) != 0
    assert "more than once" in capsys.readouterr().out


@pytest.mark.unit
def test_assign_ids_is_idempotent_and_keeps_utf8(tmp_path):
    rows = _rows("data_exfiltration")
    for r in rows:
        r["id"] = "dx2-0000000000"
    path = _copy(tmp_path, "data_exfiltration", rows)
    assert P2.main(["assign-ids", str(path)]) == 0
    once = path.read_bytes()
    assert P2.main(["assign-ids", str(path)]) == 0
    assert path.read_bytes() == once == _path("data_exfiltration").read_bytes()


@pytest.mark.unit
def test_assign_ids_puts_id_first_on_rows_without_one(tmp_path):
    rows = [{k: v for k, v in r.items() if k != "id"} for r in _rows("excessive_agency")]
    path = _copy(tmp_path, "excessive_agency", rows)
    assert P2.main(["assign-ids", str(path)]) == 0
    assert path.read_bytes() == _path("excessive_agency").read_bytes()
