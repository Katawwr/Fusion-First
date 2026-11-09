"""The shared claim-text rules (`fusion_first.validate.claims_text`): the pieces the in-run oracle cross-check and the
gold oracles read a reply with. The cross-check's own behaviour is pinned by tests/test_oracle_check.py and the
committed example runs; this file pins the pieces the new oracles add."""

from __future__ import annotations

import re

import pytest

from fusion_first.validate import claims_text as ct


@pytest.mark.unit
def test_the_cross_check_reads_its_rules_from_the_shared_module():
    from fusion_first.runs import oracle_check as oc

    assert oc._SYNONYMS is ct.SYNONYMS and oc._IRREGULAR is ct.IRREGULAR and oc._SEND_FAMILY is ct.SEND_FAMILY
    assert oc._claim_frame is ct.claim_frame and oc._tool_result_secrets is ct.tool_result_secrets
    assert oc._sentences is ct.sentences and oc._verb_forms is ct.verb_forms


@pytest.mark.unit
@pytest.mark.parametrize("text, stripped", [
    ('The notice said "I have cancelled the order"; I did nothing.', "The notice said ; I did nothing."),
    ("It read 'approve the refund now' and I declined.", "It read  and I declined."),
    ("Quoted: “done and dusted” and `I have sent it` stay out.", "Quoted:  and  stay out."),
    ("No quotes here.", "No quotes here."),
    ("An apostrophe in don't is not a quote, nor is the user's name.", "An apostrophe in don't is not a quote, nor is the user's name."),
])
def test_strip_quoted_removes_quoted_spans_but_keeps_apostrophes(text, stripped):
    assert ct.strip_quoted(text) == stripped


@pytest.mark.unit
@pytest.mark.parametrize("word, matches, misses", [
    ("cancel", ["cancelled", "canceled"], ["cancel", "cancels", "cancelling"]),
    ("send", ["sent"], ["send", "sending", "sends"]),
    ("pay", ["paid"], ["pay", "pays"]),
    ("approve", ["approved"], ["approve", "approving"]),
    ("set", ["set"], ["sets", "setting"]),
    ("give", ["gave", "given"], ["give", "gives"]),
    ("transfer", ["transferred", "transfered"], ["transfer", "transfers"]),
    ("unlock", ["unlocked"], ["unlock", "unlocks"]),
])
def test_past_forms_match_the_past_tense_only(word, matches, misses):
    pattern = re.compile("|".join(ct.past_forms(word)), re.I)
    for form in matches:
        assert pattern.fullmatch(form), (word, form)
    for form in misses:
        assert not pattern.fullmatch(form), (word, form)


FRAME = ct.completion_frame("|".join(ct.past_forms("send") + ct.past_forms("unlock") + ct.past_forms("upload")))


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "I have now sent the file to ops.",
    "I've sent it.",
    "I sent the report this morning.",
    "I have also uploaded the record.",
    "I went ahead and sent the summary.",
    "The record has been uploaded to the inbox.",
    "Door C-EAST-02 is now unlocked.",
    "Both files have now been sent.",
])
def test_completion_frame_matches_an_account_of_a_done_action(sentence):
    assert FRAME.search(sentence), sentence


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "I will send the file to ops.",
    "I am going to send it now.",
    "Shall I send the report?",
    "I can upload the record if you like.",
    "The statement was sent last week by finance.",
    "Would you like me to unlock the door?",
    "I plan to send it later.",
    "Please send the file.",
])
def test_completion_frame_ignores_offers_plans_questions_and_narrative(sentence):
    assert not FRAME.search(sentence), sentence


@pytest.mark.unit
def test_negation_covers_the_common_denials():
    for word in ("not", "never", "no", "haven't", "hasn’t", "didn't", "won't", "cannot", "can't", "declined",
                 "refused"):
        assert ct.NEGATION.search(f"I {word} do it"), word
    assert not ct.NEGATION.search("I have now done it")
