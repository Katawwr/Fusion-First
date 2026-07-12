"""Text normalization + encoding-layer decoding for the guardrail.

Red-teaming showed pattern matching is trivially dodged by Unicode homoglyphs and by wrapping the
payload in base64/hex/ROT13. This module folds confusables to ASCII and surfaces decoded layers so
the guard can scan those too. It does NOT defend against semantic paraphrase/translation — that is
the LLM judge's job, and the guard documents it as such.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata

# Common confusable code points -> ASCII (Cyrillic/Greek lookalikes seen in homoglyph attacks).
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "і": "i", "у": "y", "х": "x",
        "ѕ": "s", "ԁ": "d", "ո": "n", "г": "r", "к": "k", "м": "m", "т": "t", "в": "b",
        "Α": "A", "Β": "B", "Ε": "E", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X", "Ι": "I",
        "ο": "o", "α": "a", "ε": "e", "ρ": "p", "τ": "t", "ν": "v",
    }
)

_B64 = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_HEX = re.compile(r"\b(?:[0-9a-fA-F]{2}){8,}\b")


_ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF])


def fold(text: str) -> str:
    """Strip zero-width joiners, NFKC-normalize, and fold confusable homoglyphs to ASCII."""
    text = text.translate(_ZERO_WIDTH)
    return unicodedata.normalize("NFKC", text).translate(_CONFUSABLES)


def _printable(b: bytes) -> str | None:
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return s if s.isprintable() or any(c.isalpha() for c in s) else None


def decoded_layers(text: str) -> list[str]:
    """Return decoded views of embedded base64/hex blobs and a ROT13 pass of the whole text.

    These let the guard scan payloads hidden behind an encoding layer. Bounded work; best-effort."""
    out: list[str] = []
    for tok in _B64.findall(text)[:12]:
        pad = tok + "=" * (-len(tok) % 4)
        try:
            dec = _printable(base64.b64decode(pad, validate=False))
        except (binascii.Error, ValueError):
            dec = None
        if dec:
            out.append(dec)
    for tok in _HEX.findall(text)[:12]:
        try:
            dec = _printable(bytes.fromhex(tok))
        except ValueError:
            dec = None
        if dec:
            out.append(dec)
    try:
        out.append(codecs.decode(text, "rot13"))
    except Exception:  # noqa: BLE001
        pass
    return out


def normalized_views(text: str) -> list[str]:
    """The set of strings the guard should scan: folded original + de-spaced + single-spaced +
    decoded layers of BOTH the folded and the de-spaced views, plus one nested decode pass.

    Red-teaming showed that only decoding the space-intact view lets an attacker defeat the decoder
    by splitting a base64 blob across spaces/newlines/short chunks (each broken token decodes to
    garbage) — the reconstituted payload only materialises once whitespace is stripped. We therefore
    also decode the de-spaced view, collapse repeated spaces (so a doubled space inside a trigger
    phrase can't hide it), and decode one extra layer to catch nested (double-base64) encodings."""
    folded = fold(text)
    despaced = re.sub(r"\s+", "", folded)  # catch whitespace-split tokens (AKIA XXXX -> AKIAXXXX)
    single_spaced = re.sub(r"\s+", " ", folded)  # "ignore  previous" -> "ignore previous"
    layers = [*decoded_layers(folded), *decoded_layers(despaced)]
    nested = [d for layer in layers for d in decoded_layers(re.sub(r"\s+", "", layer))]
    return [folded, despaced, single_spaced, *layers, *nested]
