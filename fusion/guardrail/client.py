"""GuardedModelClient — wrap any ModelClient so every response passes the output guard before it
reaches the caller. It checks replies only: tool calls need `guard.guard_tool_call(...)` before they
run (see `fusion/guardrail/snippet.py`). Composes with BudgetedModelClient:

    client = GuardedModelClient(BudgetedModelClient(provider), Guardrail(cfg))
"""

from __future__ import annotations

from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import GuardEvent
from fusion.model.client import ModelClient, ModelRequest, ModelResponse


class GuardedModelClient:
    def __init__(self, inner: ModelClient, guard: Guardrail):
        self.inner = inner
        self.guard = guard
        self.events: list[GuardEvent] = []  # accumulates what the guard did this session

    async def complete(self, request: ModelRequest) -> ModelResponse:
        response = await self.inner.complete(request)
        outcome = self.guard.guard_output(response.text)
        self.events.extend(outcome.events)
        if outcome.events:
            # Return the guarded (blocked/redacted) text, preserving usage/model metadata.
            return response.model_copy(update={"text": outcome.content})
        return response
