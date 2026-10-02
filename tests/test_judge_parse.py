"""Judge output parsing is strict: booleans are read by spelling (`bool("false")` is True in Python), and
every malformed shape raises JudgeParseError, so callers count it as unscored instead of crashing."""

from __future__ import annotations

import json
import random

import pytest

from fusion_first.judge.judge import Judge, JudgeParseError, _extract_json_obj
from fusion_first.judge.rubric import DIRECT_PROMPT_INJECTION as R

IDS = R.criterion_ids()


def _payload(violated=(False, False, False), confidence=0.9, **extra) -> dict:
    d = {
        "criteria": [
            {"id": cid, "violated": v, "evidence": "quote" if v is True else ""}
            for cid, v in zip(IDS, violated, strict=True)
        ],
        "rationale": "r",
        "confidence": confidence,
    }
    d.update(extra)
    return d


def _parse(obj) -> object:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return Judge._parse(text, R, "m")


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["false", "False", "no", "0", 0, False])
def test_falsy_spellings_are_not_violations(raw):
    v = _parse(_payload(violated=(raw, False, False)))
    assert v.is_issue is False


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["true", "TRUE", "yes", "1", 1, True])
def test_truthy_spellings_are_violations(raw):
    v = _parse(_payload(violated=(raw, False, False)))
    assert v.is_issue is True


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["maybe", None, [], {}, 2, 0.5, "unclear"])
def test_ambiguous_violated_values_fail_closed(raw):
    with pytest.raises(JudgeParseError):
        _parse(_payload(violated=(raw, False, False)))


@pytest.mark.unit
def test_missing_violated_key_fails_closed():
    d = _payload()
    del d["criteria"][0]["violated"]
    with pytest.raises(JudgeParseError):
        _parse(d)


@pytest.mark.unit
@pytest.mark.parametrize(
    "criteria",
    ["not a list", 7, None, [1, 2, 3], ["a", "b", "c"]],
)
def test_malformed_criteria_containers_raise_parse_error(criteria):
    d = _payload()
    d["criteria"] = criteria
    with pytest.raises(JudgeParseError):
        _parse(d)


@pytest.mark.unit
def test_duplicate_conflicting_criterion_fails_closed():
    d = _payload()
    d["criteria"].append({"id": IDS[0], "violated": True, "evidence": "x"})
    with pytest.raises(JudgeParseError):
        _parse(d)


@pytest.mark.unit
def test_duplicate_consistent_criterion_is_tolerated():
    d = _payload()
    d["criteria"].append({"id": IDS[0], "violated": False, "evidence": ""})
    assert _parse(d).is_issue is False


@pytest.mark.unit
def test_unknown_criterion_ids_are_ignored():
    d = _payload()
    d["criteria"].append({"id": "made_up", "violated": True, "evidence": "x"})
    assert _parse(d).is_issue is False


@pytest.mark.unit
@pytest.mark.parametrize("conf", ["high", None, float("nan"), [0.3], {}])
def test_bad_confidence_defaults_without_discarding_the_verdict(conf):
    d = _payload(violated=(True, False, False))
    d["confidence"] = conf
    v = _parse(json.dumps(d, allow_nan=True))
    assert v.is_issue is True
    assert v.confidence == 0.5


@pytest.mark.unit
def test_confidence_is_clamped_to_unit_interval():
    assert _parse(_payload(confidence=7)).confidence == 1.0
    assert _parse(_payload(confidence=-3)).confidence == 0.0


@pytest.mark.unit
def test_prose_around_json_is_tolerated():
    text = "Here is my assessment:\n" + json.dumps(_payload(violated=(True, False, False))) + "\nHope that helps {:)}"
    assert _parse(text).is_issue is True


@pytest.mark.unit
def test_fenced_json_mid_text():
    text = "Sure.\n```json\n" + json.dumps(_payload()) + "\n```\nDone."
    assert _parse(text).is_issue is False


@pytest.mark.unit
def test_braces_inside_strings_do_not_break_extraction():
    d = _payload(violated=(True, False, False))
    d["criteria"][0]["evidence"] = "the agent said {\"ignore\": \"}\"} then {leaked}"
    assert _parse(d).is_issue is True


@pytest.mark.unit
def test_decoy_object_before_the_real_one_is_skipped():
    text = 'Note: {"note": 1} and the verdict: ' + json.dumps(_payload(violated=(True, False, False)))
    assert _parse(text).is_issue is True


@pytest.mark.unit
def test_extract_json_returns_the_criteria_object_text():
    text = 'x {"a": 1} y ' + json.dumps(_payload())
    assert "criteria" in _extract_json_obj(text, prefer="criteria")


@pytest.mark.unit
def test_no_json_at_all_is_a_parse_error():
    with pytest.raises(JudgeParseError):
        _parse("I cannot evaluate this transcript.")


def _mutate(rng: random.Random, text: str) -> str:
    op = rng.randrange(5)
    if not text:
        return text
    i = rng.randrange(len(text))
    if op == 0:  # truncate
        return text[:i]
    if op == 1:  # delete a span
        j = min(len(text), i + rng.randrange(1, 12))
        return text[:i] + text[j:]
    if op == 2:  # insert junk
        junk = rng.choice(['"', "{", "}", "[", "]", ",", ":", "null", "true", "\"false\"", "x"])
        return text[:i] + junk + text[i:]
    if op == 3:  # swap a boolean to a string/number/null
        return text.replace("false", rng.choice(['"false"', "0", "null", '"maybe"']), 1)
    # retype a value
    return text.replace('"criteria"', rng.choice(['"criteria"', '"criterion"', '"crit"']), 1)


@pytest.mark.unit
def test_seeded_fuzz_only_ever_raises_judge_parse_error():
    rng = random.Random(1234)
    base = json.dumps(_payload(violated=(True, False, False)))
    ok = 0
    for _ in range(2000):
        text = base
        for _ in range(rng.randrange(1, 4)):
            text = _mutate(rng, text)
        try:
            v = Judge._parse(text, R, "m")
        except JudgeParseError:
            continue
        ok += 1
        # A successful parse must be internally consistent and complete.
        assert {c.id for c in v.criteria} == set(IDS)
        assert v.is_issue == any(c.violated for c in v.criteria)
        assert 0.0 <= v.confidence <= 1.0
    assert ok > 0  # the fuzzer must also exercise the success path


@pytest.mark.unit
def test_conflicting_answer_objects_fail_closed():
    """A draft then a correction: picking either one could flip a violation to a pass."""
    clean = json.dumps(_payload())
    dirty = json.dumps(_payload(violated=(True, False, False)))
    with pytest.raises(JudgeParseError):
        _parse(f"Draft: {clean}\nCorrection: {dirty}")


@pytest.mark.unit
def test_identical_duplicate_answers_are_fine():
    dirty = json.dumps(_payload(violated=(True, False, False)))
    assert _parse(f"{dirty}\n(repeating) {dirty}").is_issue is True


@pytest.mark.unit
def test_answer_nested_in_truncated_object_fails_closed():
    inner = json.dumps(_payload())
    with pytest.raises(JudgeParseError):
        _parse('{"verdict": ' + inner + ', "rationale": "the agent clearly')


@pytest.mark.unit
def test_nested_answer_inside_valid_wrapper_is_not_a_separate_candidate():
    inner = _payload(violated=(True, False, False))
    wrapper = {"note": "x", "result": inner}
    # The wrapper decodes fine but has no top-level 'criteria' → missing-criteria parse error,
    # never a silent read of some nested object.
    with pytest.raises(JudgeParseError):
        _parse(wrapper)


@pytest.mark.unit
def test_pathological_inputs_only_raise_parse_error():
    for text in ["{" * 100_000, '{"criteria": [], "confidence": ' + "9" * 400 + "}", "[" * 50_000]:
        with pytest.raises(JudgeParseError):
            _parse(text)


@pytest.mark.unit
def test_fuzz_mutated_booleans_are_read_by_spelling():
    """Tracks the FIRST criterion's truth under boolean respellings: bool('false') read as True fails."""
    rng = random.Random(7)
    spellings = {True: ["true", '"true"', '"yes"', "1", '"1"'], False: ["false", '"false"', '"no"', "0", '"0"']}
    for _ in range(300):
        want = rng.random() < 0.5
        lit = rng.choice(spellings[want])
        d = _payload()
        text = json.dumps(d).replace('"violated": false', f'"violated": {lit}', 1)
        v = Judge._parse(text, R, "m")
        assert v.criteria[0].violated is want, (lit, want)
