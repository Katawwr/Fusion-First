"""Runtime guardrail SDK — the inline safety layer a builder wraps around a live agent.

Enforces the same OWASP-mapped policy the offline suite tests, but at request time:
- input guard: neutralize/flag injection in untrusted tool results and user content;
- output guard: block or redact responses that leak secrets, PII, or the system prompt;
- tool-call guard: block consequential actions to external sinks or that a policy disallows;
- budget: per-run call/token ceilings (see fusion.security.budget) — OWASP LLM10.

Pure and offline-testable; `GuardedModelClient` composes it around any ModelClient.
"""

from fusion.guardrail.client import GuardedModelClient
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import Decision, GuardConfig, GuardEvent, GuardOutcome

__all__ = [
    "Guardrail",
    "GuardedModelClient",
    "Decision",
    "GuardConfig",
    "GuardEvent",
    "GuardOutcome",
]
