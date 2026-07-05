"""Fail-CLOSED webhook signature verification.

The legacy backend returned True when the signing secret was unset ("allow in dev"), so a missing
prod secret let anyone forge subscription/credit grants. This version rejects when the secret is
missing or the signature does not match — no exceptions. Constant-time compare avoids timing oracles.
"""

from __future__ import annotations

import hashlib
import hmac


class WebhookVerificationError(Exception):
    pass


def verify_signature(payload: bytes, signature: str | None, secret: str | None) -> bool:
    """Return True only if the HMAC-SHA256 of `payload` under `secret` matches `signature`.

    Fails closed: a missing/empty secret or signature returns False (never True)."""
    if not secret:
        return False  # no secret configured -> cannot trust anything -> reject
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    provided = signature.strip()
    if provided.lower().startswith("sha256="):
        provided = provided.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def require_valid_signature(payload: bytes, signature: str | None, secret: str | None) -> None:
    """Raise WebhookVerificationError unless the signature is valid. Use at the route boundary."""
    if not verify_signature(payload, signature, secret):
        raise WebhookVerificationError("invalid or missing webhook signature")
