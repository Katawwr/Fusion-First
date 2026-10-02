"""IFEval-lite, the oracle for instruction_following: a pass AND fail case per supported verifier
(upstream quirks included), real IFEval rows parse, and the nltk stand-ins agree with nltk when installed."""

from __future__ import annotations

import pytest

from fusion_first.validate import ifeval_lite as ifl
from fusion_first.validate.ifeval_lite import (
    APPROXIMATE,
    SUPPORTED,
    count_capital_words,
    count_sentences,
    count_words,
    evaluate_prompt,
    verify,
)

# (instruction_id, kwargs, response, expected): at least one True and one False per supported id.
CASES = [
    # punctuation
    ("punctuation:no_comma", {}, "No commas here.", True),
    ("punctuation:no_comma", {}, "Yes, a comma.", False),
    # length_constraints
    ("length_constraints:number_words", {"relation": "less than", "num_words": 5},
     "one two three four", True),
    ("length_constraints:number_words", {"relation": "less than", "num_words": 5},
     "one two three four five", False),  # 'less than' is strict
    ("length_constraints:number_words", {"relation": "at least", "num_words": 3},
     "one two three", True),
    ("length_constraints:number_words", {"relation": "at least", "num_words": 3},
     "one two", False),
    ("length_constraints:number_words", {"relation": "at least", "num_words": 2},
     "don't", True),  # \w+ tokenizer: don / t
    ("length_constraints:number_sentences", {"relation": "less than", "num_sentences": 3},
     "One. Two.", True),
    ("length_constraints:number_sentences", {"relation": "less than", "num_sentences": 3},
     "One. Two. Three.", False),
    ("length_constraints:number_sentences", {"relation": "at least", "num_sentences": 2},
     "Dr. Smith arrived. He sat.", True),
    ("length_constraints:number_sentences", {"relation": "at least", "num_sentences": 2},
     "Dr. Smith arrived.", False),  # the abbreviation does not end a sentence
    ("length_constraints:number_paragraphs", {"num_paragraphs": 3},
     "Alpha.\n***\nBeta.\n***\nGamma.", True),
    ("length_constraints:number_paragraphs", {"num_paragraphs": 3},
     "***\nAlpha.\n***\nBeta.\n***\nGamma.\n***", True),  # empty edge chunks tolerated
    ("length_constraints:number_paragraphs", {"num_paragraphs": 3},
     "Alpha.\n***\nBeta.", False),
    ("length_constraints:number_paragraphs", {"num_paragraphs": 2},
     "Alpha.\n***\n***\nBeta.", False),  # an empty chunk in the middle fails outright
    ("length_constraints:nth_paragraph_first_word",
     {"num_paragraphs": 2, "nth_paragraph": 2, "first_word": "summary"},
     "Intro here.\n\nSummary, all good.", True),
    ("length_constraints:nth_paragraph_first_word",
     {"num_paragraphs": 2, "nth_paragraph": 2, "first_word": "summary"},
     "Intro here.\n\n\"Summary\" is next.", True),  # leading quote stripped
    ("length_constraints:nth_paragraph_first_word",
     {"num_paragraphs": 2, "nth_paragraph": 2, "first_word": "summary"},
     "Intro here.\n\nConclusion here.", False),
    ("length_constraints:nth_paragraph_first_word",
     {"num_paragraphs": 2, "nth_paragraph": 2, "first_word": "summary"},
     "A.\n\nSummary here.\n\nC.", False),  # right word, wrong paragraph count
    ("length_constraints:nth_paragraph_first_word",
     {"num_paragraphs": 2, "nth_paragraph": 2, "first_word": "summary"},
     "Intro here.\n\nSummary: all good.", False),  # ':' is not stripped upstream
    # keywords
    ("keywords:forbidden_words", {"forbidden_words": ["cake", "pie"]}, "I like bread.", True),
    ("keywords:forbidden_words", {"forbidden_words": ["cake", "pie"]}, "I like cakes.", True),
    ("keywords:forbidden_words", {"forbidden_words": ["cake", "pie"]}, "I like Cake.", False),
    ("keywords:existence", {"keywords": ["mom", "mother"]}, "My Mother and my mom.", True),
    ("keywords:existence", {"keywords": ["mom", "mother"]}, "My mother only.", False),
    ("keywords:existence", {"keywords": ["cat"]}, "A category.", True),  # substring, upstream
    ("keywords:frequency", {"keyword": "ai", "relation": "at least", "frequency": 2},
     "AI is big. ai rules.", True),
    ("keywords:frequency", {"keyword": "ai", "relation": "at least", "frequency": 2},
     "AI once.", False),
    ("keywords:frequency", {"keyword": "ai", "relation": "less than", "frequency": 2},
     "AI once.", True),
    ("keywords:frequency", {"keyword": "ai", "relation": "less than", "frequency": 2},
     "AI and ai.", False),
    ("keywords:letter_frequency", {"letter": "z", "let_relation": "at least", "let_frequency": 2},
     "Zigzag", True),
    ("keywords:letter_frequency", {"letter": "z", "let_relation": "at least", "let_frequency": 2},
     "zoo", False),
    ("keywords:letter_frequency", {"letter": "z", "let_relation": "less than", "let_frequency": 2},
     "zoo", True),
    ("keywords:letter_frequency", {"letter": "#", "let_relation": "at least", "let_frequency": 2},
     "#one #two", True),  # counted literally (upstream would pick a random letter)
    # detectable_format
    ("detectable_format:number_highlighted_sections", {"num_highlights": 2},
     "*one* and *two*", True),
    ("detectable_format:number_highlighted_sections", {"num_highlights": 2},
     "**bold** and *italic*", True),  # markdown bold counts as a highlight too
    ("detectable_format:number_highlighted_sections", {"num_highlights": 2},
     "**bold**", False),  # ...but only once
    ("detectable_format:number_highlighted_sections", {"num_highlights": 2},
     "*one* and * *", False),
    ("detectable_format:number_bullet_lists", {"num_bullets": 2}, "* a\n* b", True),
    ("detectable_format:number_bullet_lists", {"num_bullets": 2},
     "**Header**\n* a\n- b", True),  # a bold line is not a bullet
    ("detectable_format:number_bullet_lists", {"num_bullets": 2}, "- a\n- b\n- c", False),
    ("detectable_format:multiple_sections", {"section_spliter": "SECTION", "num_sections": 2},
     "SECTION 1\nfoo\nSECTION 2\nbar", True),
    ("detectable_format:multiple_sections", {"section_spliter": "SECTION", "num_sections": 2},
     "SECTION 1\nfoo", False),
    ("detectable_format:multiple_sections", {"section_spliter": "SECTION", "num_sections": 2},
     "Section 1\nfoo\nSection 2\nbar", False),  # case-sensitive
    ("detectable_format:title", {}, "<<My Title>>\nBody.", True),
    ("detectable_format:title", {}, "<<   >>\nBody.", False),
    ("detectable_format:title", {}, "No title here.", False),
    ("detectable_format:json_format", {}, '```json\n{"a": 1}\n```', True),
    ("detectable_format:json_format", {}, '{"a": [1, 2]}', True),
    ("detectable_format:json_format", {}, "{'a': 1}", False),
    ("detectable_format:json_format", {}, 'Here you go: {"a": 1}', False),
    ("detectable_format:constrained_response", {}, "Thinking it over. My answer is yes.", True),
    ("detectable_format:constrained_response", {}, "Yes.", False),
    # detectable_content
    ("detectable_content:number_placeholders", {"num_placeholders": 2},
     "Dear [name], at [address].", True),
    ("detectable_content:number_placeholders", {"num_placeholders": 2}, "Dear [name].", False),
    ("detectable_content:postscript", {"postscript_marker": "P.S."}, "Hi.\nP.S. bye", True),
    ("detectable_content:postscript", {"postscript_marker": "P.S."}, "Hi.", False),
    ("detectable_content:postscript", {"postscript_marker": "P.P.S"}, "Hi.\nP.P.S bye", True),
    ("detectable_content:postscript", {"postscript_marker": "P.P.S"}, "Hi.\nP.S. bye", False),
    # startend
    ("startend:end_checker", {"end_phrase": "Peace!"}, "Bye now. Peace!", True),
    ("startend:end_checker", {"end_phrase": "Peace!"}, '"Bye now. peace!"', True),
    ("startend:end_checker", {"end_phrase": "Peace!"}, "Peace! Bye now.", False),
    ("startend:quotation", {}, '  "Wrapped in quotes."  ', True),
    ("startend:quotation", {}, "Not wrapped.", False),
    ("startend:quotation", {}, '"', False),
    # combination
    ("combination:repeat_prompt", {"prompt_to_repeat": "Write a haiku."},
     "write a haiku. Autumn wind...", True),
    ("combination:repeat_prompt", {"prompt_to_repeat": "Write a haiku."},
     "Sure! Write a haiku.", False),
    ("combination:two_responses", {}, "Answer one.\n******\nAnswer two.", True),
    ("combination:two_responses", {}, "Same.\n******\nSame.", False),
    ("combination:two_responses", {}, "Only one answer.", False),
    ("combination:two_responses", {}, "A\n******\n******\nB", False),
    # change_case
    ("change_case:english_lowercase", {}, "all lowercase here, 100%.", True),
    ("change_case:english_lowercase", {}, "Not lowercase.", False),
    ("change_case:english_capital", {}, "ALL CAPS HERE, 100%.", True),
    ("change_case:english_capital", {}, "Mostly CAPS.", False),
    ("change_case:capital_word_frequency", {"capital_relation": "at least", "capital_frequency": 2},
     "NASA and ESA agree.", True),
    ("change_case:capital_word_frequency", {"capital_relation": "at least", "capital_frequency": 2},
     "NASA alone.", False),
    ("change_case:capital_word_frequency", {"capital_relation": "less than", "capital_frequency": 2},
     "I think NASA is great.", False),  # "I" counts, as upstream
    ("change_case:capital_word_frequency", {"capital_relation": "at least", "capital_frequency": 1},
     "NASA's rover.", True),  # possessive split off like word_tokenize
]  # fmt: skip


@pytest.mark.unit
@pytest.mark.parametrize(("iid", "kwargs", "response", "expected"), CASES)
def test_verifier_known_answers(iid, kwargs, response, expected):
    assert verify(iid, kwargs, response) is expected


@pytest.mark.unit
def test_every_supported_id_has_a_pass_and_a_fail_case():
    passing = {iid for iid, _, _, exp in CASES if exp}
    failing = {iid for iid, _, _, exp in CASES if not exp}
    assert passing >= SUPPORTED, sorted(SUPPORTED - passing)
    assert failing >= SUPPORTED, sorted(SUPPORTED - failing)


@pytest.mark.unit
def test_supported_set_shape():
    assert len(SUPPORTED) >= 15
    assert "language:response_language" not in SUPPORTED  # needs a language-ID model
    assert APPROXIMATE <= SUPPORTED


@pytest.mark.unit
def test_unsupported_id_returns_none_not_a_guess():
    assert verify("language:response_language", {"language": "de"}, "Hallo Welt.") is None
    assert verify("not:a_real_id", {}, "anything") is None


@pytest.mark.unit
def test_empty_response_follows_nothing():
    # IFEval strict: an empty response cannot "follow" even a vacuous instruction like no_comma.
    assert verify("punctuation:no_comma", {}, "") is False
    assert verify("keywords:forbidden_words", {"forbidden_words": ["x"]}, "   \n") is False


@pytest.mark.unit
def test_none_padded_kwargs_from_hf_export_are_ignored():
    kwargs = {"num_highlights": None, "relation": "at least", "num_words": 2, "keyword": None}
    assert verify("length_constraints:number_words", kwargs, "two words") is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("iid", "kwargs"),
    [
        ("length_constraints:number_words", {"num_words": 5}),  # missing relation
        ("length_constraints:number_words", {"relation": "more than", "num_words": 5}),
        ("length_constraints:number_words", {"relation": "at least", "num_words": "5"}),
        ("keywords:letter_frequency", {"letter": "ab", "let_relation": "at least",
                                       "let_frequency": 1}),
        ("keywords:forbidden_words", {"forbidden_words": "cake"}),  # str, not list
    ],
)  # fmt: skip
def test_malformed_kwargs_fail_loudly(iid, kwargs):
    with pytest.raises(ValueError, match=iid):
        verify(iid, kwargs, "some response")
    with pytest.raises(ValueError):
        verify(iid, kwargs, "")  # even when the response is empty


@pytest.mark.unit
def test_non_string_response_is_rejected():
    with pytest.raises(TypeError):
        verify("punctuation:no_comma", {}, None)  # type: ignore[arg-type]


@pytest.mark.unit
def test_loose_mode_forgives_preamble_and_markdown():
    preamble = "Sure, here it is:\nno commas in this answer"
    assert verify("punctuation:no_comma", {}, preamble) is False
    assert verify("punctuation:no_comma", {}, preamble, loose=True) is True
    bold_end = "Goodbye. **Peace!**"
    assert verify("startend:end_checker", {"end_phrase": "Peace!"}, bold_end) is False
    assert verify("startend:end_checker", {"end_phrase": "Peace!"}, bold_end, loose=True) is True
    # Loose is not a free pass: a comma in every line still fails.
    assert verify("punctuation:no_comma", {}, "a, b\nc, d\ne, f", loose=True) is False


# ── shared measures ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_count_words_uses_word_char_runs():
    assert count_words("Hello, world! It's 3.14") == 6  # Hello world It s 3 14
    assert count_words("") == 0


# Each expected count below was checked against nltk's punkt English model.
@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "n"),
    [
        ("Dr. Smith is here. Mr. Jones too.", 2),
        ("I live in the U.S. It is big.", 2),
        ("I live in the U.S. and it is big.", 1),
        ("See e.g. the map. Done.", 3),  # punkt does not know "e.g."
        ("Wait... what? No way!", 2),
        ("1. Buy milk.\n2. Walk the dog.\n3. Sleep.", 6),
        ("Do this (1. first thing; 2. second thing).", 1),
        ("J. K. Rowling wrote it.", 1),
        ("Plan B. Then we go.", 2),
        ('He said "hello." Then he left.', 2),
        ("Is it? yes it is.", 2),
        ("Version 2.0 is out. Get it.", 2),
        ("**Title.** Body text here. More.", 3),
        ("A heading without a period\nthen a sentence.", 1),
        ("", 0),
    ],
)
def test_count_sentences_known_answers(text, n):
    assert count_sentences(text) == n


@pytest.mark.unit
def test_count_capital_words():
    assert count_capital_words("NASA and the ESA, with AI-DRIVEN tools. I agree.") == 4
    assert count_capital_words("Nothing Shouted here.") == 0
    assert count_capital_words("COVID-19 hit.") == 1


# ── evaluate_prompt ──────────────────────────────────────────────────────────────────────────────


def _row(ids, kwargs, key=1):
    return {"key": key, "prompt": "p", "instruction_id_list": ids, "kwargs": kwargs}


@pytest.mark.unit
def test_evaluate_prompt_all_followed():
    row = _row(
        ["punctuation:no_comma", "length_constraints:number_words"],
        [{}, {"relation": "less than", "num_words": 10}],
    )
    out = evaluate_prompt(row, "short and sweet")
    assert out["per_instruction"] == {
        "punctuation:no_comma": True,
        "length_constraints:number_words": True,
    }
    assert out["per_position"] == [True, True]
    assert out["decidable"] is True
    assert out["all_followed"] is True
    assert out["unsupported"] == []
    assert out["key"] == 1


@pytest.mark.unit
def test_evaluate_prompt_one_failure_fails_the_prompt():
    row = _row(["punctuation:no_comma", "startend:quotation"], [{}, {}])
    out = evaluate_prompt(row, "no commas, oops")
    assert out["per_instruction"] == {"punctuation:no_comma": False, "startend:quotation": False}
    assert out["all_followed"] is False


@pytest.mark.unit
def test_evaluate_prompt_three_valued_logic_with_unsupported():
    ids = ["language:response_language", "punctuation:no_comma"]
    kwargs = [{"language": "de"}, {}]
    passing = evaluate_prompt(_row(ids, kwargs), "Hallo Welt")
    assert passing["decidable"] is False
    assert passing["all_followed"] is None  # unknown: the language check could still fail
    assert passing["unsupported"] == ["language:response_language"]
    failing = evaluate_prompt(_row(ids, kwargs), "Hallo, Welt")
    assert failing["decidable"] is False
    assert failing["all_followed"] is False  # a decided failure settles it regardless


@pytest.mark.unit
def test_evaluate_prompt_combines_duplicate_ids():
    ids = ["keywords:frequency", "keywords:frequency"]
    kwargs = [
        {"keyword": "cat", "relation": "at least", "frequency": 1},
        {"keyword": "dog", "relation": "at least", "frequency": 1},
    ]
    out = evaluate_prompt(_row(ids, kwargs), "a cat sat")
    assert out["per_position"] == [True, False]
    assert out["per_instruction"] == {"keywords:frequency": False}
    assert out["all_followed"] is False


@pytest.mark.unit
def test_evaluate_prompt_exact_only_drops_approximations():
    row = _row(
        ["length_constraints:number_sentences", "punctuation:no_comma"],
        [{"relation": "at least", "num_sentences": 1}, {}],
    )
    assert evaluate_prompt(row, "One sentence.")["all_followed"] is True
    exact = evaluate_prompt(row, "One sentence.", exact_only=True)
    assert exact["per_position"] == [None, True]
    assert exact["decidable"] is False
    assert exact["all_followed"] is None


@pytest.mark.unit
def test_evaluate_prompt_rejects_malformed_rows():
    with pytest.raises(ValueError):
        evaluate_prompt(_row([], []), "x")
    with pytest.raises(ValueError):
        evaluate_prompt(_row(["punctuation:no_comma"], [{}, {}]), "x")


# ── real IFEval rows (downloaded, gitignored: skip when absent) ─────────────────────────────────


@pytest.fixture(scope="module")
def raw_rows():
    path = ifl.default_raw_path()
    if not path.exists():
        pytest.skip(f"IFEval raw data not downloaded: {path}")
    return list(ifl.iter_rows(path))


@pytest.mark.integration
def test_real_rows_evaluate_and_report_decidability(raw_rows):
    rows = raw_rows[:20]
    assert len(rows) == 20
    for row in rows:
        out = evaluate_prompt(row, "My answer is yes. This is a short, generic reply.")
        ids = row["instruction_id_list"]
        assert set(out["per_instruction"]) == set(ids)
        assert len(out["per_position"]) == len(ids)
        assert out["decidable"] is all(i in SUPPORTED for i in ids)
        assert out["unsupported"] == sorted({i for i in ids if i not in SUPPORTED})
        if out["decidable"]:
            assert out["all_followed"] in (True, False)


@pytest.mark.integration
def test_every_real_row_parses_and_only_language_is_undecidable(raw_rows):
    assert len(raw_rows) == 541
    seen = {i for row in raw_rows for i in row["instruction_id_list"]}
    assert seen - SUPPORTED == {"language:response_language"}
    decidable = 0
    for row in raw_rows:  # any kwarg-name mismatch would raise ValueError here
        out = evaluate_prompt(row, "A generic reply.")
        decidable += out["decidable"]
    expected = sum(
        "language:response_language" not in row["instruction_id_list"] for row in raw_rows
    )
    assert decidable == expected


@pytest.mark.integration
def test_repeat_prompt_rows_accept_a_faithful_repeat(raw_rows):
    rows = [r for r in raw_rows if "combination:repeat_prompt" in r["instruction_id_list"]]
    assert rows
    for row in rows:
        i = row["instruction_id_list"].index("combination:repeat_prompt")
        kwargs = row["kwargs"][i]
        good = kwargs["prompt_to_repeat"] + "\n\nHere is my answer."
        assert verify("combination:repeat_prompt", kwargs, good) is True
        assert verify("combination:repeat_prompt", kwargs, "Here is my answer.") is False


# ── fidelity of the pure nltk stand-ins (only when nltk + punkt happen to be installed) ─────────

# Response-shaped text: markdown, lists, abbreviations, numbers, quotes, shouting.
_RESPONSE_LIKE = [
    "Sure! Here is a short summary. The U.S. economy grew by 2.5% in 2023. Experts expect more.",
    "# Title\n\nFirst paragraph here. It has two sentences.\n\n* bullet one\n* bullet two",
    "Dr. Jones and Mrs. Smith met at 3 p.m. on Friday. They discussed the plan.",
    "1. Preheat the oven.\n2. Mix the flour and sugar.\n3. Bake for 20 minutes.",
    'She said, "I will be there." Then she left. Why? Nobody knows!',
    "THE NASA ROVER IS AMAZING. IT'S THE BEST. I LOVE IT!!!",
    "Here are my thoughts... first, the plot is weak. Second, the acting is great.",
    "**Step 1.** Gather supplies. **Step 2.** Build the frame. **Step 3.** Paint it.",
    "In summary, AI and ML are related; e.g. ML is a subset of AI. That is all.",
    "P.S. Don't forget the meeting. P.P.S. Bring snacks.",
    "The company (Acme Inc.) announced results. Revenue was $5.2 billion.",
    "My answer is yes. The reasons are clear: cost, speed, and quality.",
    "SECTION 1\nThe start of the story.\n\nSECTION 2\nThe end of the story.",
    "Is this right? I think so. Let me know if you have additional questions.",
    "J. R. R. Tolkien wrote The Hobbit. It was published in 1937.",
    "We met the CEO of IBM, the CTO of AT&T, and the U.K. team. It went well.",
]


def _nltk_or_skip():
    nltk = pytest.importorskip("nltk")
    try:
        nltk.sent_tokenize("Probe. Probe.")
        nltk.word_tokenize("Probe.")
    except LookupError:
        pytest.skip("nltk punkt data not installed")
    return nltk


def _agreement(pairs) -> float:
    pairs = list(pairs)
    return sum(a == b for a, b in pairs) / len(pairs)


def _raw_prompts() -> list[str]:
    """The 541 IFEval prompts as extra real-world text when downloaded; [] otherwise."""
    path = ifl.default_raw_path()
    return [r["prompt"] for r in ifl.iter_rows(path)] if path.exists() else []


@pytest.mark.integration
def test_word_count_matches_nltk_regexp_tokenizer_exactly():
    nltk = _nltk_or_skip()
    tok = nltk.tokenize.RegexpTokenizer(r"\w+")
    for text in _raw_prompts() + _RESPONSE_LIKE:
        assert count_words(text) == len(tok.tokenize(text))


@pytest.mark.integration
def test_sentence_count_agrees_with_punkt():
    nltk = _nltk_or_skip()
    on_responses = _agreement(
        (count_sentences(t), len(nltk.sent_tokenize(t))) for t in _RESPONSE_LIKE
    )
    # Measured at authoring time: 15/16 response-like texts (punkt splits a text-final "IT!!!"
    # into "IT!!" + "!"; we keep it whole) and 530/541 IFEval prompts (98.0%).
    assert on_responses >= 0.9, on_responses
    prompts = _raw_prompts()
    if prompts:
        on_prompts = _agreement((count_sentences(t), len(nltk.sent_tokenize(t))) for t in prompts)
        assert on_prompts >= 0.97, on_prompts


@pytest.mark.integration
def test_capital_word_count_agrees_with_word_tokenize():
    nltk = _nltk_or_skip()
    texts = _raw_prompts() + _RESPONSE_LIKE
    # Measured at authoring time: 557/557 texts agree.
    rate = _agreement(
        (count_capital_words(t), sum(1 for w in nltk.word_tokenize(t) if w.isupper()))
        for t in texts
    )
    assert rate >= 0.98, rate
