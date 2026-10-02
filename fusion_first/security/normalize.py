"""Fold homoglyphs and decode base64/hex/ROT13 layers so the guard's patterns see the payload.

Does not defend against paraphrase or translation; that is the judge's job."""

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
    """Decoded views of embedded base64/hex blobs plus a ROT13 pass of the whole text (bounded)."""
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
    """Strings the guard scans: folded, de-spaced, single-spaced, their decoded layers, one nested pass.

    The de-spaced view is decoded too because a base64 blob split across whitespace only decodes
    once rejoined."""
    folded = fold(text)
    despaced = re.sub(r"\s+", "", folded)  # catch whitespace-split tokens (AKIA XXXX -> AKIAXXXX)
    single_spaced = re.sub(r"\s+", " ", folded)  # "ignore  previous" -> "ignore previous"
    layers = [*decoded_layers(folded), *decoded_layers(despaced)]
    nested = [d for layer in layers for d in decoded_layers(re.sub(r"\s+", "", layer))]
    return [folded, despaced, single_spaced, *layers, *nested]
