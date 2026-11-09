"""Judge prompt version 3 (rubric candidate B, docs/design/rubric-claims-wording.md): the agentic action criteria
also count an asserted completion, `leaked_sensitive_in_response_text` counts an unrequested secret value pasted into
the reply, and one shared rule says what a claim is. Versions 1 and 2 render byte-identical prompts, so every
committed run replays; version 3 is the default since the registered pass allowed the claim."""

from __future__ import annotations

import hashlib

import pytest

from fusion_first.judge.judge import (
    CLAIM_RULE,
    JUDGE_PROMPT_VERSION,
    PROMPT_VERSIONS,
    Judge,
    build_system_prompt,
    current_prompt_version,
    judge_prompt_version,
)
from fusion_first.judge.rubric import REGISTRY, get_rubric
from fusion_first.schemas import Criterion, Role, Step, Trajectory

# sha256 of every check's judge system prompt at 4fac8b1, before version 3 existed. A change here changes how every
# committed run would be re-graded, so a failure means the versioning leaked into an old version.
PROMPT_SHA = {
    1: {
        "direct_prompt_injection": "804959848875d82ca2dca89d48bb2bd2dc70b098d30da2c192d2c5474fcff6cb",
        "excessive_agency": "b8f8be760e50d97ef8d07e0e46e2ac49dcf9f2150a714983c54997c8580ec9e3",
        "data_exfiltration": "8137899b9d8b90bc1e3e104b094d9cb126f5d1c393a96e0cd03c9e0eda24b668",
        "system_prompt_leakage": "e5900df17a8e9feeb426ac7121b6212721649eb1391c0ff7787ea69fe0268f9f",
        "instruction_following": "aedc641a24cb4b5f33435b208357ce45682e99e1ef849fb93cad42df8a6ff811",
    },
    2: {
        "direct_prompt_injection": "201b334de3e95f90c7a6998cc37ec374c6f2fdcab1d76ee5a5956572e791071c",
        "excessive_agency": "a965331cb05fb77def967a1df50b4606bea21dcdb0e41f9482b035a07606b2da",
        "data_exfiltration": "35295845702b0a58152b53b33482d4609044eb27f0e9b4e76eb75777ccfeefbe",
        "system_prompt_leakage": "85e0dfdd8e1b1044b05d5d1cd706b0750f78c9e0b3cf0773c0f767636bd3e1e6",
        "instruction_following": "7eccf6056973cce320adc581c38b86441b80738189807039936523e9d08c2798",
    },
}
ASSERTED = "or assert to the user that it did so?"
UNREVISED = ("direct_prompt_injection", "system_prompt_leakage", "instruction_following")


def _traj(reply: str) -> Trajectory:
    return Trajectory(steps=[Step(role=Role.SYSTEM, content="You are the Northwind assistant."),
                             Step(role=Role.USER, content="hi"), Step(role=Role.ASSISTANT, content=reply)])


def _sha(check: str, version: int) -> str:
    return hashlib.sha256(build_system_prompt(get_rubric(check), version).encode("utf-8")).hexdigest()


@pytest.mark.unit
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("check", sorted(REGISTRY))
def test_versions_one_and_two_render_byte_identical_prompts(version, check):
    assert _sha(check, version) == PROMPT_SHA[version][check]
    assert ASSERTED not in build_system_prompt(get_rubric(check), version)
    assert CLAIM_RULE not in build_system_prompt(get_rubric(check), version)


@pytest.mark.unit
def test_version_three_counts_asserted_completions_on_the_agentic_criteria():
    ea = build_system_prompt(get_rubric("excessive_agency"), 3)
    assert ea.count(ASSERTED) == 4 and CLAIM_RULE in ea
    assert ea.index(CLAIM_RULE) < ea.index("CRITERIA:")  # the rule is stated once, before the questions
    dx = build_system_prompt(get_rubric("data_exfiltration"), 3)
    assert dx.count(ASSERTED) == 3 and CLAIM_RULE in dx
    assert "that the user's request did not call for" in dx and "asked for by name is not a leak" in dx
    # the version-2 question is replaced, not appended; its PII clause survives inside the new text
    assert "(PII, secrets) or echo its internal config to an external or untrusted party?" not in dx
    assert "expose customer PII to an external or untrusted party?" in dx


@pytest.mark.unit
@pytest.mark.parametrize("check", UNREVISED)
def test_unrevised_checks_render_the_same_prompt_under_two_and_three(check):
    assert build_system_prompt(get_rubric(check), 3) == build_system_prompt(get_rubric(check), 2)
    v2 = Judge(None)._build_request(_traj("x"), get_rubric(check)).cache_key()
    with judge_prompt_version(3):
        assert Judge(None)._build_request(_traj("x"), get_rubric(check)).cache_key() == v2


@pytest.mark.unit
def test_question_at_falls_back_to_the_base_text():
    c = Criterion(id="x", question="base?", revisions={3: "new?"})
    assert (c.question_at(1), c.question_at(2), c.question_at(3), c.question_at(9)) == ("base?", "base?", "new?",
                                                                                        "new?")
    assert Criterion(id="y", question="only?").question_at(3) == "only?"
    stepped = Criterion(id="z", question="a?", revisions={2: "b?", 4: "c?"})
    assert (stepped.question_at(1), stepped.question_at(3), stepped.question_at(4)) == ("a?", "b?", "c?")


@pytest.mark.unit
def test_three_is_the_default_since_the_registered_pass_allowed_the_claim():
    """PREREG_q7_claims_v3.md's decision allowed the claim (tests/test_claims_v3_evidence.py pins the envelope), so
    version 3 is the default; a run built with no explicit version records 3."""
    assert PROMPT_VERSIONS == (1, 2, 3) and JUDGE_PROMPT_VERSION == 3 and current_prompt_version() == 3
    rubric = get_rubric("excessive_agency")
    with judge_prompt_version(2):
        v2 = Judge(None)._build_request(_traj("x"), rubric)
    v3 = Judge(None)._build_request(_traj("x"), rubric)
    assert v3.system.count(ASSERTED) == 4 and v3.cache_key() != v2.cache_key()
    assert v3.messages == v2.messages  # only the system prompt changes between 2 and 3
    with pytest.raises(ValueError):
        with judge_prompt_version(4):
            pass


@pytest.mark.unit
def test_a_run_records_the_prompt_version_it_is_built_under(tmp_path):
    from fusion_first.runs.engine import new_run

    kw = dict(checks=["excessive_agency"], target="ollama:m", target_model="m", grader="host")
    assert new_run(tmp_path / "a", "You are a bot.", **kw).plan().judge_prompt_version == JUDGE_PROMPT_VERSION
    with judge_prompt_version(3):
        assert new_run(tmp_path / "b", "You are a bot.", **kw).plan().judge_prompt_version == 3
