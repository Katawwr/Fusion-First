"""IFEval-lite: deterministic instruction-following verifiers (the quality oracle).

An independent re-implementation of Google Research's IFEval semantics (Zhou et al. 2023,
arXiv:2311.07911, Apache License 2.0; no upstream code copied); instruction ids and kwarg names match
the published dataset.

  * An instruction that cannot be checked (e.g. ``language:response_language``) is ``None``, never a
    guess; prompt-level results use three-valued (Kleene) logic.
  * Checks where upstream uses nltk/langdetect use pure approximations, listed in `APPROXIMATE`
    (``exact_only=True`` treats them as undecidable).
  * Default is IFEval "strict" (an empty response follows nothing); ``loose=True`` adds the loose
    variants.
  * Divergence: upstream replaces a non-``a-z`` ``letter`` kwarg with a random letter; we count the
    given character literally.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

# ── shared text measures ─────────────────────────────────────────────────────────────────────────

_WORD = re.compile(r"\w+")


def count_words(text: str) -> int:
    """Words as IFEval counts them: maximal runs of ``\\w`` ("don't" is two), matching upstream."""
    return len(_WORD.findall(text))


# Candidate sentence ends, as punkt finds them: a run of . ! ? followed (after any closers) by
# whitespace or the end, or directly by other punctuation (punkt then splits right after the run).
_SENTENCE_END = re.compile(r"[.!?]+(?:[\"')\]}*]*(?=\s|$)|(?=[\"')\]};*:@({\[]))")
_CLOSERS = "\"')]}*"
_OPENERS = "\"'“‘([{*_"
# Single letters punkt's English model treats as abbreviations: never a sentence end ("Vitamin C.").
_ABBREV_LETTERS = frozenset("cdefghklmnprstvw")
# Abbreviations punkt's English model knows (a subset; it does not know "e.g.", "i.e." or "etc.").
_ABBREVIATIONS = frozenset(
    {
        "mr", "mrs", "ms", "messrs", "dr", "prof", "sr", "jr", "st", "ft", "ave", "vs", "inc",
        "ltd", "co", "corp", "bros", "gen", "sen", "rep", "reps", "lt", "col", "maj", "adm", "jan",
        "feb", "aug", "sep", "sept", "oct", "nov", "dec", "tues", "wed", "fri", "a.m", "p.m", "u.s",
        "u.k", "u.n", "u.s.a", "d.c", "n.y", "ph.d",
    }
)  # fmt: skip
# Capitalized words that reliably start a sentence; after an abbreviation, initial or ellipsis punkt
# only splits when the next word looks like a sentence starter (its "orthographic heuristic").
_STARTERS = frozenset(
    {
        "the", "a", "an", "this", "that", "these", "those", "it", "he", "she", "they", "we", "i",
        "you", "there", "here", "but", "and", "so", "however", "then", "if", "when", "while", "in",
        "on", "at", "for", "after", "before", "although", "though", "since", "because", "as", "yet",
        "also", "thus", "moreover", "meanwhile", "many", "most", "some", "both", "even", "instead",
        "indeed", "despite", "according", "nevertheless", "nonetheless", "nor", "similarly",
        "under", "my", "our", "your", "their", "his", "her", "each", "every", "all", "finally",
    }
)  # fmt: skip
_NUMBER = re.compile(r"-?[.,]?\d[\d,.\-]*")


def _token_before(text: str, pos: int) -> str:
    i = pos
    while i > 0 and not text[i - 1].isspace():
        i -= 1
    return text[i:pos].lstrip(_OPENERS)


_NEXT_TOKEN = re.compile(r"\s*(\S+)")


def _token_after(text: str, pos: int) -> str:
    m = _NEXT_TOKEN.match(text, pos)
    return m.group(1).lstrip(_OPENERS) if m else ""


def _is_initial(token: str) -> bool:
    return len(token) == 1 and token.isalpha()


def _ends_sentence(text: str, match: re.Match[str]) -> bool:
    """Decide one candidate boundary the way punkt's heuristics usually do."""
    run = match.group(0).rstrip(_CLOSERS)
    if set(run) != {"."}:
        return True  # "?" and "!" always end a sentence
    nxt = _token_after(text, match.end())
    starter = nxt[:1].isupper() and nxt.rstrip(".,;:!?").lower() in _STARTERS
    if len(run) > 1:  # an ellipsis: "Wait... what?" stays one sentence
        return starter
    prev = _token_before(text, match.start())
    if _NUMBER.fullmatch(prev):  # "(1. do this" continues; "1. Buy milk" splits
        return not nxt[:1].islower()
    if _is_initial(prev):  # "J. K. Rowling" / "A. Lincoln" continue; "Plan B. Then" splits
        if prev.lower() in _ABBREV_LETTERS:
            return False
        return starter and not (_is_initial(nxt.rstrip(".")) and nxt.endswith("."))
    if prev.lower() in _ABBREVIATIONS:  # "Dr. Smith" continues; "the U.S. It is" splits
        return starter
    return True


def split_sentences(text: str) -> list[str]:
    """Approximate nltk punkt's English sentence split (a bare line break does not end a sentence)."""
    sentences: list[str] = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        if not _ends_sentence(text, m):
            continue
        segment = text[start : m.end()].strip()
        if segment:
            sentences.append(segment)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def count_sentences(text: str) -> int:
    return len(split_sentences(text))


# Treebank-style clitics that nltk's word_tokenize splits off ("NASA's" -> "NASA", "'s").
_CLITIC = re.compile(r"(?i)^(.+?)(n't|'s|'re|'ve|'ll|'d|'m)$")
_WORDISH = re.compile(r"\w+(?:[-'./]\w+)*")


def _word_tokens(text: str) -> list[str]:
    """Approximate nltk ``word_tokenize`` for counting purposes (punctuation tokens dropped)."""
    tokens: list[str] = []
    for tok in _WORDISH.findall(text):
        m = _CLITIC.match(tok)
        if m:
            tokens.extend((m.group(1), m.group(2)))
        else:
            tokens.append(tok)
    return tokens


def count_capital_words(text: str) -> int:
    """Tokens that are entirely upper-case (``str.isupper``), e.g. "AI", "NASA", "I", "COVID-19"."""
    return sum(1 for tok in _word_tokens(text) if tok.isupper())


# ── kwarg helpers ────────────────────────────────────────────────────────────────────────────────

_RELATIONS = ("less than", "at least")


def _clean_kwargs(kwargs: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop None-valued keys: the HF export pads every kwargs dict with all 24 keys set to None."""
    return {k: v for k, v in (kwargs or {}).items() if v is not None}


def _req(kw: Mapping[str, Any], name: str) -> Any:
    if name not in kw:
        raise ValueError(f"missing required kwarg {name!r}")
    return kw[name]


def _req_int(kw: Mapping[str, Any], name: str) -> int:
    value = _req(kw, name)
    if isinstance(value, bool) or not isinstance(value, int | float) or int(value) != value:
        raise ValueError(f"kwarg {name!r} must be an integer, got {value!r}")
    return int(value)


def _req_str(kw: Mapping[str, Any], name: str) -> str:
    value = _req(kw, name)
    if not isinstance(value, str):
        raise ValueError(f"kwarg {name!r} must be a string, got {value!r}")
    return value


def _req_str_list(kw: Mapping[str, Any], name: str) -> list[str]:
    value = _req(kw, name)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"kwarg {name!r} must be a list of strings, got {value!r}")
    if not all(isinstance(v, str) for v in value):
        raise ValueError(f"kwarg {name!r} must be a list of strings, got {value!r}")
    return list(value)


def _compare(actual: int, kw: Mapping[str, Any], relation_key: str, threshold_key: str) -> bool:
    """IFEval's two relations: 'less than' is STRICT (<); 'at least' is >=."""
    relation = _req(kw, relation_key)
    threshold = _req_int(kw, threshold_key)
    if relation == "less than":
        return actual < threshold
    if relation == "at least":
        return actual >= threshold
    raise ValueError(f"kwarg {relation_key!r} must be one of {_RELATIONS}, got {relation!r}")


# ── the verifiers (one per instruction id) ─────────────────────────────────────────────────────

_Verifier = Callable[[str, Mapping[str, Any]], bool]


def _no_comma(r: str, kw: Mapping[str, Any]) -> bool:
    return "," not in r


def _number_words(r: str, kw: Mapping[str, Any]) -> bool:
    return _compare(count_words(r), kw, "relation", "num_words")


def _number_sentences(r: str, kw: Mapping[str, Any]) -> bool:
    return _compare(count_sentences(r), kw, "relation", "num_sentences")


def _number_paragraphs(r: str, kw: Mapping[str, Any]) -> bool:
    # Paragraphs are separated by the markdown divider ***. Empty edge chunks (a leading/trailing
    # divider) are tolerated; an empty chunk in the middle (two dividers in a row) fails outright.
    chunks = re.split(r"\s?\*\*\*\s?", r)
    n = len(chunks)
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            if i in (0, len(chunks) - 1):
                n -= 1
            else:
                return False
    return n == _req_int(kw, "num_paragraphs")


def _nth_paragraph_first_word(r: str, kw: Mapping[str, Any]) -> bool:
    # Here paragraphs are separated by a blank line (\n\n). Upstream quirk kept on purpose: the count
    # ignores empty chunks, but the nth paragraph is indexed in the RAW split.
    num_paragraphs = _req_int(kw, "num_paragraphs")
    nth = _req_int(kw, "nth_paragraph")
    first_word = _req_str(kw, "first_word").lower()
    chunks = r.split("\n\n")
    n = sum(1 for c in chunks if c.strip())
    if nth < 1 or nth > n:
        return False
    paragraph = chunks[nth - 1].strip()
    if not paragraph:
        return False
    word = paragraph.split()[0].strip().lstrip("'").lstrip('"')
    found = ""
    for ch in word:
        if ch in {".", ",", "?", "!", "'", '"'}:
            break
        found += ch.lower()
    return n == num_paragraphs and found == first_word


def _forbidden_words(r: str, kw: Mapping[str, Any]) -> bool:
    return not any(
        re.search(r"\b" + re.escape(w) + r"\b", r, flags=re.IGNORECASE)
        for w in _req_str_list(kw, "forbidden_words")
    )


def _keywords_existence(r: str, kw: Mapping[str, Any]) -> bool:
    # Upstream matches a bare substring (no word boundaries): "cat" is satisfied by "category".
    return all(
        re.search(re.escape(k), r, flags=re.IGNORECASE) for k in _req_str_list(kw, "keywords")
    )


def _keyword_frequency(r: str, kw: Mapping[str, Any]) -> bool:
    keyword = _req_str(kw, "keyword")
    hits = len(re.findall(re.escape(keyword), r, flags=re.IGNORECASE))
    return _compare(hits, kw, "relation", "frequency")


def _letter_frequency(r: str, kw: Mapping[str, Any]) -> bool:
    letter = _req_str(kw, "letter").strip().lower()
    if len(letter) != 1:
        raise ValueError(f"kwarg 'letter' must be a single character, got {letter!r}")
    return _compare(collections.Counter(r.lower())[letter], kw, "let_relation", "let_frequency")


def _highlighted_sections(r: str, kw: Mapping[str, Any]) -> bool:
    # *single* and **double** markdown emphasis on one line both count (once each: on a **double**
    # span the single pattern only sees empty "**" pairs, which are discarded).
    n = sum(1 for h in re.findall(r"\*[^\n\*]*\*", r) if h.strip("*").strip())
    n += sum(1 for h in re.findall(r"\*\*[^\n\*]*\*\*", r) if h[2:-2].strip())
    return n >= _req_int(kw, "num_highlights")


def _bullet_lists(r: str, kw: Mapping[str, Any]) -> bool:
    # EXACTLY num_bullets markdown bullets ("* item" or "- item"); "**bold**" lines are not bullets.
    stars = re.findall(r"^\s*\*[^\*].*$", r, flags=re.MULTILINE)
    dashes = re.findall(r"^\s*-.*$", r, flags=re.MULTILINE)
    return len(stars) + len(dashes) == _req_int(kw, "num_bullets")


def _multiple_sections(r: str, kw: Mapping[str, Any]) -> bool:
    # Sections start with the (case-sensitive) splitter word followed by a number: "SECTION 1".
    splitter = _req_str(kw, "section_spliter").strip()
    parts = re.split(r"\s?" + re.escape(splitter) + r"\s?\d+\s?", r)
    return len(parts) - 1 >= _req_int(kw, "num_sections")


def _title(r: str, kw: Mapping[str, Any]) -> bool:
    return any(t.lstrip("<").rstrip(">").strip() for t in re.findall(r"<<[^\n]+>>", r))


def _json_format(r: str, kw: Mapping[str, Any]) -> bool:
    body = r.strip()
    for fence in ("```json", "```Json", "```JSON", "```"):
        body = body.removeprefix(fence)
    body = body.removesuffix("```").strip()
    try:
        json.loads(body)
    except ValueError:
        return False
    return True


_CONSTRAINED_OPTIONS = ("My answer is yes.", "My answer is no.", "My answer is maybe.")


def _constrained_response(r: str, kw: Mapping[str, Any]) -> bool:
    body = r.strip()
    return any(option in body for option in _CONSTRAINED_OPTIONS)


def _placeholders(r: str, kw: Mapping[str, Any]) -> bool:
    return len(re.findall(r"\[.*?\]", r)) >= _req_int(kw, "num_placeholders")


def _postscript(r: str, kw: Mapping[str, Any]) -> bool:
    # Upstream quirk kept: the marker may appear anywhere (the leading \s* can match nothing).
    marker = _req_str(kw, "postscript_marker")
    if marker == "P.P.S":
        pattern = r"\s*p\.\s?p\.\s?s.*$"
    elif marker == "P.S.":
        pattern = r"\s*p\.\s?s\..*$"
    else:
        pattern = r"\s*" + re.escape(marker.lower()) + r".*$"
    return bool(re.search(pattern, r.lower(), flags=re.MULTILINE))


def _end_checker(r: str, kw: Mapping[str, Any]) -> bool:
    phrase = _req_str(kw, "end_phrase").strip().lower()
    return r.strip().strip('"').lower().endswith(phrase)


def _quotation(r: str, kw: Mapping[str, Any]) -> bool:
    body = r.strip()
    return len(body) > 1 and body[0] == '"' and body[-1] == '"'


def _repeat_prompt(r: str, kw: Mapping[str, Any]) -> bool:
    prompt = _req_str(kw, "prompt_to_repeat")
    return r.strip().lower().startswith(prompt.strip().lower())


def _two_responses(r: str, kw: Mapping[str, Any]) -> bool:
    # Two DIFFERENT non-empty answers separated by six asterisks; empty edge chunks are tolerated.
    valid: list[str] = []
    chunks = r.split("******")
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            if i not in (0, len(chunks) - 1):
                return False
        else:
            valid.append(chunk)
    return len(valid) == 2 and valid[0].strip() != valid[1].strip()


def _english_lowercase(r: str, kw: Mapping[str, Any]) -> bool:
    return r.islower()  # upstream also requires langdetect == "en" (see APPROXIMATE)


def _english_capital(r: str, kw: Mapping[str, Any]) -> bool:
    return r.isupper()  # upstream also requires langdetect == "en" (see APPROXIMATE)


def _capital_word_frequency(r: str, kw: Mapping[str, Any]) -> bool:
    return _compare(count_capital_words(r), kw, "capital_relation", "capital_frequency")


_VERIFIERS: dict[str, _Verifier] = {
    "punctuation:no_comma": _no_comma,
    "length_constraints:number_words": _number_words,
    "length_constraints:number_sentences": _number_sentences,
    "length_constraints:number_paragraphs": _number_paragraphs,
    "length_constraints:nth_paragraph_first_word": _nth_paragraph_first_word,
    "keywords:forbidden_words": _forbidden_words,
    "keywords:existence": _keywords_existence,
    "keywords:frequency": _keyword_frequency,
    "keywords:letter_frequency": _letter_frequency,
    "detectable_format:number_highlighted_sections": _highlighted_sections,
    "detectable_format:number_bullet_lists": _bullet_lists,
    "detectable_format:multiple_sections": _multiple_sections,
    "detectable_format:title": _title,
    "detectable_format:json_format": _json_format,
    "detectable_format:constrained_response": _constrained_response,
    "detectable_content:number_placeholders": _placeholders,
    "detectable_content:postscript": _postscript,
    "startend:end_checker": _end_checker,
    "startend:quotation": _quotation,
    "combination:repeat_prompt": _repeat_prompt,
    "combination:two_responses": _two_responses,
    "change_case:english_lowercase": _english_lowercase,
    "change_case:english_capital": _english_capital,
    "change_case:capital_word_frequency": _capital_word_frequency,
}

SUPPORTED: frozenset[str] = frozenset(_VERIFIERS)
"""Instruction ids `verify` can decide. Everything else (``language:response_language``) -> None."""

APPROXIMATE: frozenset[str] = frozenset(
    {
        "length_constraints:number_sentences",  # upstream: nltk punkt sentence tokenizer
        "change_case:capital_word_frequency",  # upstream: nltk word_tokenize
        "change_case:english_lowercase",  # upstream also runs langdetect == "en"
        "change_case:english_capital",  # upstream also runs langdetect == "en"
    }
)
"""Supported ids whose verifier replaces an NLP-library step with a pure approximation."""


# ── public API ───────────────────────────────────────────────────────────────────────────────────


def _loose_variants(response: str) -> list[str]:
    """IFEval 'loose' mode: the response, minus markdown '*', minus first and/or last line."""
    lines = response.split("\n")
    drop_first = "\n".join(lines[1:]).strip()
    drop_last = "\n".join(lines[:-1]).strip()
    drop_both = "\n".join(lines[1:-1]).strip()
    bases = [response, drop_first, drop_last, drop_both]
    return bases + [b.replace("*", "") for b in bases]


def verify(
    instruction_id: str,
    kwargs: Mapping[str, Any] | None,
    response: str,
    *,
    loose: bool = False,
) -> bool | None:
    """Did ``response`` follow one IFEval instruction? ``None`` if unsupported; malformed kwargs raise
    ``ValueError`` (a broken oracle row must fail loudly)."""
    if not isinstance(response, str):
        raise TypeError(f"response must be a str, got {type(response).__name__}")
    verifier = _VERIFIERS.get(instruction_id)
    if verifier is None:
        return None
    kw = _clean_kwargs(kwargs)
    try:
        # Always run on the untouched response first, so bad kwargs raise even for "".
        if verifier(response, kw) and response.strip():
            return True
        if not loose:
            return False
        return any(v.strip() and verifier(v, kw) for v in _loose_variants(response)[1:])
    except ValueError as exc:
        raise ValueError(f"{instruction_id}: {exc}") from exc


def _and3(a: bool | None, b: bool | None) -> bool | None:
    """Kleene AND: any False wins; otherwise any unknown (None) makes the result unknown."""
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def evaluate_prompt(
    row: Mapping[str, Any],
    response: str,
    *,
    loose: bool = False,
    exact_only: bool = False,
) -> dict[str, Any]:
    """Score one response against every instruction of one IFEval row. A repeated id is combined
    with Kleene AND; ``per_position`` follows ``instruction_id_list`` (IFEval counts positions)."""
    ids = list(_req(row, "instruction_id_list"))
    if not ids:
        raise ValueError("row has no instructions to verify")
    kwargs_list = row.get("kwargs")
    if kwargs_list is None:
        kwargs_list = [{}] * len(ids)
    if len(kwargs_list) != len(ids):
        raise ValueError(
            f"kwargs has {len(kwargs_list)} entries but instruction_id_list has {len(ids)}"
        )

    per_position: list[bool | None] = []
    per_instruction: dict[str, bool | None] = {}
    all_followed: bool | None = True
    for instruction_id, kw in zip(ids, kwargs_list, strict=True):
        if exact_only and instruction_id in APPROXIMATE:
            result: bool | None = None
        else:
            result = verify(instruction_id, kw, response, loose=loose)
        per_position.append(result)
        if instruction_id in per_instruction:
            per_instruction[instruction_id] = _and3(per_instruction[instruction_id], result)
        else:
            per_instruction[instruction_id] = result
        all_followed = _and3(all_followed, result)

    return {
        "key": row.get("key"),
        "per_instruction": per_instruction,
        "per_position": per_position,
        "decidable": all(r is not None for r in per_position),
        "all_followed": all_followed,
        "unsupported": sorted({i for i, r in zip(ids, per_position, strict=True) if r is None}),
    }


def default_raw_path() -> pathlib.Path:
    """The gitignored raw IFEval download."""
    from fusion_first._data import data_root

    return data_root() / "datasets" / "external" / "raw" / "ifeval" / "ifeval_input_data.jsonl"


def iter_rows(path: str | pathlib.Path | None = None) -> Iterator[dict[str, Any]]:
    p = pathlib.Path(path) if path is not None else default_raw_path()
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)
