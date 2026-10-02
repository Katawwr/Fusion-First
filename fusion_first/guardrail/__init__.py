"""Runtime guardrail: input fence, output redact/block, and tool-call policy around a live agent.

A deterministic defense-in-depth layer, not a complete detector: it catches literal and lightly
obfuscated attacks but not semantic evasions (paraphrase, translation, spelled-out PII). Never present
it as sufficient on its own; pair it with the judge.
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
