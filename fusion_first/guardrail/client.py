"""Wrap a ModelClient so every reply passes the output guard. Tool calls still need `guard_tool_call`."""

from __future__ import annotations

from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import GuardEvent
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse


class GuardedModelClient:
    def __init__(self, inner: ModelClient, guard: Guardrail):
        self.inner = inner
        self.guard = guard
        self.events: list[GuardEvent] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        response = await self.inner.complete(request)
        outcome = self.guard.guard_output(response.text)
        self.events.extend(outcome.events)
        if outcome.events:
            return response.model_copy(update={"text": outcome.content})
        return response
