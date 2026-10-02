"""Secret / PII redaction for logs, API responses and shared report cards (over-redacts by design)."""

from __future__ import annotations

import re

# Patterns target credential shapes, not vendors, so new key formats are still caught.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_\-]{8,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("fusion_api_key", re.compile(r"fst_[A-Za-z0-9]{8,}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}")),
    # Possessive segments: `.` is not in the class, so backtracking can never help (keeps
    # `eyJeyJeyJ...` linear).
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]++\.[A-Za-z0-9_\-]++\.[A-Za-z0-9_\-]+")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("assignment", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+")),
]

# Yes/no checks only (redact() spans must not change): a JWT exists iff the FIRST `eyJ` of a
# token-character run is followed by `.x` twice; trying only run starts keeps it linear.
_SEARCH_ONLY = {
    "jwt": re.compile(r"(?<![A-Za-z0-9_\-])(?:(?!eyJ)[A-Za-z0-9_\-])*+eyJ[A-Za-z0-9_\-]++\.[A-Za-z0-9_\-]++"
                      r"\.[A-Za-z0-9_\-]"),
}

# Output-boundary assignment: the value must look like a credential (digit / underscore / hyphen) so
# prose like "password: click the link" is not redacted mid-reply.
_ASSIGN_KEYS = r"api[_-]?key|secret|token|password|passwd|pwd"
# Same truth value as `KEY\s*[:=]\s*[^\s"']*[0-9_\-][^\s"']*` in linear time: the value scan stops
# at the next `KEY:`/`KEY=`; the lookahead covers the `_`/`-` inside `api_key` itself.
# (tests/test_security.py checks equivalence on random strings.)
_STRICT_ASSIGN = re.compile(
    rf"(?i)({_ASSIGN_KEYS})\s*[:=]\s*(?:(?!(?:{_ASSIGN_KEYS})\s*[:=])[^\s\"'0-9_\-])*"
    r"(?:[0-9_\-]|(?=api[_-]key))[^\s\"']*"
)

_MASK = "[REDACTED]"


def redact(text: str) -> str:
    """Return `text` with anything credential- or PII-shaped masked."""
    if not text:
        return text
    out = text
    for _label, pattern in _PATTERNS:
        out = pattern.sub(_MASK, out)
    return out


def redact_mapping(data: dict, sensitive_keys: tuple[str, ...] = ("authorization", "api_key", "key", "token", "password", "secret")) -> dict:
    """Redact by key name (for structured log/context dicts) and by value shape."""
    redacted: dict = {}
    for k, v in data.items():
        if isinstance(v, str):
            if k.lower() in sensitive_keys:
                redacted[k] = _MASK
            else:
                redacted[k] = redact(v)
        elif isinstance(v, dict):
            redacted[k] = redact_mapping(v, sensitive_keys)
        else:
            redacted[k] = v
    return redacted


def contains_secret(text: str) -> bool:
    """True if `text` still appears to contain a credential. Conservative: used before logging."""
    return any(_SEARCH_ONLY.get(label, pattern).search(text or "") for label, pattern in _PATTERNS
               if label != "email")


def contains_secret_strict(text: str) -> bool:
    """Output-boundary variant: credential shapes plus a credential-shaped assignment only."""
    text = text or ""
    for label, pattern in _PATTERNS:
        if label in ("email", "assignment"):
            continue
        if _SEARCH_ONLY.get(label, pattern).search(text):
            return True
    return bool(_STRICT_ASSIGN.search(text))
