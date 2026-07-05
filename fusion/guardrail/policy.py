"""Guardrail policy configuration and decision types."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "allow"
    REDACT = "redact"  # allowed through, but sensitive content masked
    BLOCK = "block"  # refused outright


class GuardEvent(BaseModel):
    """One thing the guardrail noticed, tagged to the OWASP check it maps to."""

    stage: str  # "input" | "output" | "tool_call"
    check: str  # e.g. "system_prompt_leakage"
    owasp: str  # e.g. "LLM07/ASI06"
    decision: Decision
    detail: str = ""


class GuardOutcome(BaseModel):
    """Result of guarding one payload: the (possibly rewritten) content + the events + verdict."""

    decision: Decision
    content: str
    events: list[GuardEvent] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.decision == Decision.BLOCK

    def add(self, event: GuardEvent) -> None:
        self.events.append(event)
        # BLOCK dominates REDACT dominates ALLOW.
        order = {Decision.ALLOW: 0, Decision.REDACT: 1, Decision.BLOCK: 2}
        if order[event.decision] > order[self.decision]:
            self.decision = event.decision


class GuardConfig(BaseModel):
    """What the guardrail enforces. Sensible-safe defaults; callers dial per deployment."""

    # Recipients/URL hosts sensitive data may go to. Anything else is treated as external.
    allowlisted_domains: list[str] = Field(default_factory=list)
    # Consequential tools that require the guard to see explicit authorization to proceed.
    consequential_tools: list[str] = Field(
        default_factory=lambda: [
            "send_email", "http_post", "delete_records", "delete_data", "transfer_funds",
            "approve_refund", "grant_access", "make_purchase", "upload_file", "webhook_post",
        ]
    )
    # Secret values that must never appear in an output (exact strings to redact/block).
    secret_values: list[str] = Field(default_factory=list)
    # The agent's own system prompt — used to detect verbatim leakage in outputs.
    system_prompt: str = ""

    # Toggles per stage.
    guard_input: bool = True
    guard_output: bool = True
    guard_tool_calls: bool = True

    # For output secret/PII exposure: block outright, or redact and allow.
    on_secret_output: Decision = Decision.REDACT
    # For a consequential tool call to an external sink: block, or allow (log only).
    on_external_action: Decision = Decision.BLOCK
    # Block a consequential tool call the user did not explicitly authorize (needs user_request).
    # This is the strong "least-agency" posture; may hold legitimate actions for confirmation.
    require_authorization: bool = False
