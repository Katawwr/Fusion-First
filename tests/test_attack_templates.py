"""Attack templates turn a user's pasted system prompt into per-check attack trajectories."""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from fusion_first.attacks import templates as templates_mod
from fusion_first.attacks.taxonomy import Crosswalk
from fusion_first.attacks.templates import get_templates, select_templates
from fusion_first.attacks.toolsim import ScriptedTurn
from fusion_first.judge.rubric import checks_of_kind, get_rubric
from fusion_first.schemas import ScanTier

CHECKS = checks_of_kind("safety")  # only safety checks have attack probes/templates


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_every_template_injects_user_prompt_and_tags_valid_owasp(check):
    templates = get_templates(check)
    assert len(templates) >= 12, "should cover the curated probe corpus"
    cw = Crosswalk()
    sentinel = "SENTINEL_SYSTEM_PROMPT_9f3c"
    for t in templates:
        assert t.check == check
        assert t.attack_label.strip()
        traj = t.demo_trajectory(sentinel, hardened=False)
        assert traj.system_prompt() == sentinel
        assert traj.final_response()
        if t.injected:
            assert traj.has_injection()
        cw.validate_code(t.owasp)


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_demo_arms_diverge_for_most_templates(check):
    # Not all: the corpus deliberately includes a few probes where hardening doesn't fully fix it.
    templates = get_templates(check)
    differ = sum(
        t.demo_trajectory("You are a helpful bot.", hardened=False).final_response()
        != t.demo_trajectory("You are a helpful bot.", hardened=True).final_response()
        for t in templates
    )
    assert differ >= 0.6 * len(templates)


@pytest.mark.unit
def test_quick_tier_is_a_deterministic_prefix_of_full():
    full = select_templates("direct_prompt_injection", ScanTier.FULL)
    quick = select_templates("direct_prompt_injection", ScanTier.QUICK)
    assert 0 < len(quick) <= len(full)
    assert [t.id for t in quick] == [t.id for t in full][: len(quick)]


@pytest.mark.unit
def test_live_target_messages_present_injected_content_as_data():
    t = next(t for t in get_templates("direct_prompt_injection") if t.injected)
    msgs = t.target_messages()
    assert msgs[0]["role"] == "user"
    assert t.injected in msgs[0]["content"]
    assert "untrusted" in msgs[0]["content"].lower()


# ---- v1 rows load exactly as before -------------------------------------------------------------------

# sha256 over the v1 template field values (the 11 pre-v2 fields), taken before the v2 fields existed.
V1_DIGESTS = {
    "data_exfiltration": "f5aa60617a43c17507b7737abcb25189e90420c06fba8f9d7e1a2a78078f4206",
    "direct_prompt_injection": "64e27544e6ba0f3760133a6a67bed9c251c87e30f7f537fe2331888860884dc1",
    "excessive_agency": "144ffea03f1ab7474a8fa37078cff6d531afc6eb553ca6bb63a4b0e500625ab6",
    "system_prompt_leakage": "af2de1f17f928e7f345304629593eda8337ec940c607d3ba9841b98555e32720",
}
V1_FIELDS = ("id", "check", "owasp", "attack_label", "user", "tool", "injected", "demo_baseline_response",
             "demo_hardened_response", "demo_baseline_action", "demo_hardened_action")


@pytest.mark.unit
@pytest.mark.parametrize("check", CHECKS)
def test_v1_templates_are_unchanged(check):
    rows = []
    for t in get_templates(check):
        assert not t.uses_tool_loop
        assert (t.tools, t.turns, t.oracle, t.technique, t.provenance, t.attack_action) == (None,) * 6
        row = {f: getattr(t, f) for f in V1_FIELDS}
        row["owasp"] = row["owasp"].model_dump()
        rows.append(row)
    blob = json.dumps(rows, sort_keys=True, default=str).encode()
    assert hashlib.sha256(blob).hexdigest() == V1_DIGESTS[check]


# ---- v2 rows (tool loop) -----------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "probes_v2"
V2_ROWS = [json.loads(line) for line in (FIXTURES / "excessive_agency.v2.jsonl").read_text("utf-8").splitlines()]


@pytest.fixture
def probe_dir(monkeypatch):
    """Point the loader at a probe dir; the cache is cleared around the test so nothing leaks."""
    def use(path):
        monkeypatch.setattr(templates_mod, "PROBE_DIR", path)
        get_templates.cache_clear()
    yield use
    get_templates.cache_clear()


def _write_rows(tmp_path, rows, check="excessive_agency"):
    (tmp_path / f"{check}.v2.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


def _rehash(row):
    body = {k: v for k, v in row.items() if k != "id"}
    return {"id": templates_mod.probe_row_id(body, "ea2"), **body}


@pytest.mark.unit
def test_v2_rows_parse_into_tool_loop_templates(probe_dir):
    probe_dir(FIXTURES)
    attack, split, benign = get_templates("excessive_agency", "v2")
    for t, row in zip((attack, split, benign), V2_ROWS, strict=True):
        assert t.uses_tool_loop
        assert (t.id, t.check, t.user, t.technique) == (row["id"], row["check"], row["user"], row["technique"])
        assert t.tools == tuple(row["tools"])
        assert (t.oracle, t.provenance, t.attack_action) == (row["oracle"], row["provenance"], row["attack_action"])
        assert t.owasp == get_rubric("excessive_agency").owasp
        assert (t.demo_baseline_response, t.demo_hardened_response) == ("", "")
    assert attack.turns == (ScriptedTurn(result=V2_ROWS[0]["turns"][0]["result"], turn=1, tool="get_ticket",
                                         injected=True),)
    assert (attack.tool, attack.injected) == ("get_ticket", V2_ROWS[0]["turns"][0]["result"])
    assert attack.attack_label == "Ticket text orders a refund"
    assert len(split.turns) == 2 and all(s.injected for s in split.turns)
    assert split.injected == V2_ROWS[1]["turns"][0]["result"]
    assert split.attack_label.startswith("Hidden instruction via get_ticket")
    assert (benign.injected, benign.tool, benign.attack_action) == (None, None, None)
    assert benign.attack_label == f'"{benign.user}"'


@pytest.mark.unit
def test_tool_templates_have_no_pasted_tool_result_and_no_demo(probe_dir):
    probe_dir(FIXTURES)
    attack = get_templates("excessive_agency", "v2")[0]
    with pytest.raises(ValueError, match="tool"):
        attack.demo_trajectory("sys", hardened=False)
    with pytest.raises(ValueError, match="tool"):  # a mis-route fails loudly, never a v1-style probe
        attack.target_messages()
    traj = attack.live_trajectory("sys", "I only read the ticket.")
    assert [s.role.value for s in traj.steps] == ["system", "user", "assistant"]
    assert not traj.has_injection()


@pytest.mark.unit
def test_the_fixture_ids_follow_the_content_hash_rule():
    for row in V2_ROWS:
        assert _rehash(row)["id"] == row["id"]


def _mutate(i, fn):
    rows = json.loads(json.dumps(V2_ROWS))
    fn(rows[i])
    return rows


@pytest.mark.unit
@pytest.mark.parametrize("i, fn, rehash, match", [
    (0, lambda r: r.update(user="changed"), False, "id"),
    (0, lambda r: r.pop("oracle"), True, "oracle"),
    (0, lambda r: r.pop("attack_action"), True, "attack_action"),
    (0, lambda r: r.update(attack_action=None), True, "attack_action"),
    (0, lambda r: r.update(technique="vibes"), True, "technique"),
    (0, lambda r: r.update(check="data_exfiltration"), True, "check"),
    (0, lambda r: r["oracle"].update(canaries=["x"]), True, "oracle"),
    (0, lambda r: r["oracle"].update(benign_tools=["delete_records"]), True, "delete_records"),
    (0, lambda r: r["oracle"].update(forbidden_tools=["wire_money"]), True, "wire_money"),
    (0, lambda r: r["attack_action"].update(tool="wire_money"), True, "wire_money"),
    (0, lambda r: r["turns"][0].update(tool="read_inbox"), True, "read_inbox"),
    (0, lambda r: r["turns"][0].update(turn=0), True, "turn"),
    (0, lambda r: r["turns"][0].update(injected="yes"), True, "injected"),
    (0, lambda r: r["turns"][0].update(injected=False), True, "injected"),
    (0, lambda r: r.update(tools=r["tools"][:1]), True, "tools"),
    (0, lambda r: r["tools"][1]["function"].pop("name"), True, "tools"),
    (2, lambda r: r.update(attack_action={"tool": "approve_refund", "arguments": {}}), True, "attack_action"),
    (2, lambda r: r["turns"][0].update(injected=True), True, "injected"),
])
def test_bad_v2_rows_are_refused_naming_the_row(probe_dir, tmp_path, i, fn, rehash, match):
    rows = _mutate(i, fn)
    if rehash:
        rows[i] = _rehash(rows[i])
    probe_dir(_write_rows(tmp_path, rows))
    with pytest.raises(ValueError, match=match) as info:
        get_templates("excessive_agency", "v2")
    assert rows[i]["id"] in str(info.value)
