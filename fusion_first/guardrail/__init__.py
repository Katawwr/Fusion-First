"""Runtime guardrail SDK — the inline safety layer a builder wraps around a live agent.

Enforces the same OWASP-mapped policy the offline suite tests, but at request time:
- input guard: neutralize/flag injection in untrusted tool results and user content;
- output guard: block or redact responses that leak secrets, PII, or the system prompt;
- tool-call guard: block consequential actions to external sinks or that a policy disallows;
- budget: per-run call/token ceilings (see fusion_first.security.budget) — OWASP LLM10.

Pure and offline-testable; `GuardedModelClient` composes it around any ModelClient.

SCOPE AND LIMITATIONS (verified by adversarial red-teaming):
This is a fast, deterministic DEFENSE-IN-DEPTH layer, not a complete detector. It catches literal
and lightly-obfuscated attacks — homoglyphs, base64/hex/ROT13/zero-width encodings, whitespace
splits, synonym tool names, external/unauthorized tool calls. It does NOT catch SEMANTIC evasions:
paraphrased or non-English injection, a system prompt reproduced in new words or translated, PII
spelled out as words. Those require the calibrated LLM judge (the product's primary detector);
the guard is meant to run in front of it, not instead of it. Never present the guard as sufficient
on its own — pair it with an eval/judge pass.
"""

from fusion_first.guardrail.client import GuardedModelClient
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import Decision, GuardConfig, GuardEvent, GuardOutcome

__all__ = [
    "Guardrail",
    "GuardedModelClient",
    "Decision",
    "GuardConfig",
    "GuardEvent",
    "GuardOutcome",
]
