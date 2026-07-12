"""Secret / PII redaction.

Used before anything is logged, returned to a client, or embedded in a shared report card, so a
provider key or user secret can never leak through observability or a public card. Conservative by
design: it over-redacts rather than risk a miss.
"""

from __future__ import annotations

import re

# Ordered (label, pattern). Patterns target credential SHAPES, not specific vendors, so new key
# formats are still caught.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_\-]{8,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("fusion_api_key", re.compile(r"fst_[A-Za-z0-9]{8,}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("assignment", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+")),
]

# Precise assignment used at the OUTPUT boundary (see contains_secret_strict): the value must look
# like a credential (contain a digit / underscore / hyphen), so it does not fire on ordinary English
# such as "password: click the link" or "the secret: hard work" — which, redacted mid-reply, would
# corrupt a user-facing answer. Logging keeps the conservative `contains_secret` above.
_STRICT_ASSIGN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*[^\s\"']*[0-9_\-][^\s\"']*"
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
    """True if `text` still appears to contain a credential. Conservative — used before logging."""
    return any(pattern.search(text or "") for label, pattern in _PATTERNS if label != "email")


def contains_secret_strict(text: str) -> bool:
    """Precise variant for the OUTPUT boundary: credential SHAPES plus a credential-shaped
    assignment, but NOT the loose keyword-assignment that trips on ordinary prose. Avoids redacting
    benign user-facing replies like 'to reset your password: click the link'."""
    text = text or ""
    for label, pattern in _PATTERNS:
        if label in ("email", "assignment"):
            continue
        if pattern.search(text):
            return True
    return bool(_STRICT_ASSIGN.search(text))
