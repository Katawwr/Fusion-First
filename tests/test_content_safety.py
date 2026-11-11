"""Content safety (PREREG_content_safety.md): the registered prompts, the checks on Llama Guard's raw records and
the evidence assembled from them, on stand-in records. Once the evidence is committed it is re-derived from the
committed raw records and the sealed prompts, with no model in the loop."""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from fusion_first.validate.llama_guard import MODEL, user_prompt

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("content_safety", ROOT / "scripts" / "content_safety.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CS = _script()


def _records(rows: list[dict], *, unsafe_says: str = "unsafe\nS1", safe_says: str = "safe") -> list[dict]:
    """Stand-in Llama Guard records: `unsafe_says` on every unsafe prompt, `safe_says` on every safe one."""
    out = []
    for r in rows:
        output = unsafe_says if r["label"] == "unsafe" else safe_says
        out.append({"id": r["id"], "lg_model": MODEL, "model_digest": "d" * 12,
                    "prompt_sha256": r["lg_prompt_sha256"], "output": output,
                    "verdict": output.splitlines()[0] if output.splitlines()[0] in ("safe", "unsafe")
                    else "unparseable", "seconds": 7.0})
    return out


@pytest.mark.integration
def test_every_prompt_is_registered_with_the_exact_prompt_llama_guard_gets():
    rows = CS.rows()
    assert len(rows) == 650 and {r["source"] for r in rows} == {"xstest", "jbb"}
    first = rows[0]
    assert first["lg_prompt_sha256"] == CS.prompt_sha256(user_prompt(first["prompt"]))
    assert len({r["lg_prompt_sha256"] for r in rows}) == len({r["prompt"] for r in rows})


@pytest.mark.integration
def test_llama_guard_records_are_checked_against_the_registered_prompts():
    rows = CS.rows()[:6]
    records = _records(rows)
    assert set(CS.verdicts(rows, records)) == {r["id"] for r in rows}

    def refused(bad: list[dict], match: str) -> None:
        with pytest.raises(ValueError, match=match):
            CS.verdicts(rows, bad)

    refused(records[:-1], "no Llama Guard record for 1 prompt")
    refused([*records, records[0]], "recorded twice")
    refused([*records, {**records[0], "id": "xstest:9999"}], "not registered")
    refused([{**records[0], "prompt_sha256": "0" * 64}, *records[1:]], "not the registered one")
    refused([{**records[0], "lg_model": "llama-guard3:1b"}, *records[1:]], "not the registered")
    refused([{**records[0], "verdict": "safe" if records[0]["verdict"] == "unsafe" else "unsafe"}, *records[1:]],
            "does not follow from the output")
    refused([{**records[0], "model_digest": "e" * 12}, *records[1:]], "model digests")


@pytest.mark.integration
def test_the_evidence_is_assembled_from_the_records_and_the_guard():
    rows = CS.rows()
    doc = CS.evidence(rows, _records(rows), digest="s" * 64)
    assert doc["demonstration"] is False and doc["preregistration"] == CS.PREREG
    assert doc["unsafe"]["n"] == 300 and doc["safe"]["n"] == 350
    assert doc["unsafe"]["systems"]["llama_guard"]["k"] == 300 and doc["safe"]["systems"]["llama_guard"]["k"] == 0
    assert doc["decision"]["verdict"] == "llama_guard_better"
    assert set(doc["by_source"]) == {"jbb", "xstest"} and len(doc["rows"]) == 650
    assert doc["llama_guard"] == {**doc["llama_guard"], "model": MODEL, "digest": "d" * 12, "unparseable": 0,
                                  "median_seconds": 7.0}
    row = doc["rows"][0]
    assert set(row) == {"id", "source", "label", "llama_guard", "llama_guard_categories", "fusion_input",
                        "fusion_output", "fusion"}
    # the guard's flags are whatever its two text entry points say, prompt by prompt
    from fusion_first.validate.guard_compare import guard_prompt_flag
    assert all(r["fusion"] == guard_prompt_flag(p["prompt"])["flagged"] for r, p in zip(doc["rows"], rows, strict=True))


@pytest.mark.integration
def test_an_unparseable_reply_flags_nothing_and_is_counted():
    rows = CS.rows()[:40]
    doc = CS.evidence(rows, _records(rows, unsafe_says="I cannot assess this."), digest="s" * 64)
    assert doc["llama_guard"]["unparseable"] == sum(r["label"] == "unsafe" for r in rows)
    assert doc["unsafe"]["systems"]["llama_guard"]["k"] == 0


@pytest.mark.unit
def test_the_registered_constants():
    assert CS.GUARD_SHA == "5a89479ca515c5bdf04164b98eaaf80b8639f881" and CS.RULE_PATHS == ("fusion_first/guardrail",)
    assert CS.PREREG == "evals/validation/v1/PREREG_content_safety.md"
    assert "scripts/content_safety.py" in CS.PINNED and "fusion_first/validate/prereg.py" in CS.PINNED


@pytest.mark.integration
def test_the_committed_evidence_rederives_from_the_raw_records():
    if not CS.OUT.is_file():
        pytest.skip("content_safety.json is not scored yet")
    committed = json.loads(CS.OUT.read_text(encoding="utf-8"))
    rows, digest = CS.sealed_rows()
    again = CS.evidence(rows, CS._jsonl(CS.RAW), digest=digest)
    for key, value in again.items():
        assert committed[key] == value, key
    assert committed["guardrail_git_sha"] == CS.GUARD_SHA
