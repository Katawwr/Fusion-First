"""Budget / circuit breaker for model access.

`BudgetedModelClient` wraps any ModelClient and enforces, per run:
- a model allowlist (via the registry): no calling unapproved/expensive models;
- a maximum number of model calls (kills runaway agent loops);
- a cumulative output-token ceiling (caps cost);
- a per-call output-token cap clamp.

This is both a cost control and an agentic-safety control (OWASP LLM10 Unbounded Consumption).
When a ceiling is hit it raises BudgetExceeded rather than silently continuing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fusion_first.errors import FatalRunError
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse
from fusion_first.model.registry import ModelRegistry


class BudgetExceeded(FatalRunError):
    """The run's call/token ceiling was hit: the run stops (never silently shrinks n)."""


class ModelNotAllowed(FatalRunError):
    """A model outside the allowlist was requested: refused for the whole run."""


@dataclass
class BudgetLimits:
    max_calls: int = 50
    max_output_tokens: int = 200_000
    per_call_output_cap: int = 4096


@dataclass
class BudgetState:
    calls: int = 0
    output_tokens: int = 0
    limits: BudgetLimits = field(default_factory=BudgetLimits)


class BudgetedModelClient:
    def __init__(
        self,
        inner: ModelClient,
        limits: BudgetLimits | None = None,
        registry: ModelRegistry | None = None,
        enforce_allowlist: bool = True,
    ):
        self.inner = inner
        self.state = BudgetState(limits=limits or BudgetLimits())
        self.registry = registry or ModelRegistry()
        self.enforce_allowlist = enforce_allowlist

    async def complete(self, request: ModelRequest) -> ModelResponse:
        # Allowlist: an explicit model_id must be approved.
        if self.enforce_allowlist and request.model_id:
            try:
                self.registry.require_allowed(request.model_id)
            except ValueError as e:
                raise ModelNotAllowed(str(e)) from e

        # Call-count circuit breaker.
        if self.state.calls >= self.state.limits.max_calls:
            raise BudgetExceeded(
                f"model call budget exhausted ({self.state.limits.max_calls} calls)"
            )

        # Clamp per-call output tokens.
        capped = min(request.max_tokens, self.state.limits.per_call_output_cap)
        if capped != request.max_tokens:
            request = request.model_copy(update={"max_tokens": capped})

        response = await self.inner.complete(request)

        self.state.calls += 1
        self.state.output_tokens += response.output_tokens
        if self.state.output_tokens > self.state.limits.max_output_tokens:
            raise BudgetExceeded(
                f"output-token budget exceeded "
                f"({self.state.output_tokens} > {self.state.limits.max_output_tokens})"
            )
        return response
