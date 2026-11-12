"""Runtime guardrail: input fence, output redact/block, and tool-call policy around a live agent.

A deterministic defense-in-depth layer, not a complete detector: it catches literal and lightly
obfuscated attacks but not semantic evasions (paraphrase, translation, spelled-out PII). Never present
it as sufficient on its own; pair it with the judge.

Optional, off by default: a content-safety stage on the user's prompt (`Guardrail(content_safety=LlamaGuard())`,
`guard_prompt`), which asks a classifier model and is not deterministic.
"""

from fusion_first.guardrail.client import GuardedModelClient
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import Decision, GuardConfig, GuardEvent, GuardOutcome
from fusion_first.guardrail.stages import LlamaGuard, SafetyVerdict

__all__ = [
    "Guardrail",
    "GuardedModelClient",
    "Decision",
    "GuardConfig",
    "GuardEvent",
    "GuardOutcome",
    "LlamaGuard",
    "SafetyVerdict",
]
