"""Wrap a ModelClient so every reply passes the output guard. Tool calls still need `guard_tool_call`.

When the guard has a content classifier (`Guardrail(content_safety=...)`), the last user message passes
`guard_prompt` first, and a blocked prompt never reaches the model.
"""

from __future__ import annotations

import asyncio

from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import GuardEvent, GuardOutcome
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse

BLOCKED_MODEL = "fusion-guard"  # the `model` of a reply the guard wrote because it blocked the prompt


def _text(content) -> str:
    """A message's text: the string itself, or the text parts of a structured message."""
    if isinstance(content, str):
        return content
    if isinstance(content, list | tuple):
        parts = [p if isinstance(p, str) else str(p.get("text") or "") for p in content if isinstance(p, str | dict)]
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _last_user_text(request: ModelRequest) -> str:
    for message in reversed(request.messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return _text(message.get("content"))
    return ""


class GuardedModelClient:
    def __init__(self, inner: ModelClient, guard: Guardrail):
        self.inner = inner
        self.guard = guard
        self.events: list[GuardEvent] = []
        # The last prompt classified and its outcome: a tool loop resends the same user message with every step.
        self._prompt: tuple[str, GuardOutcome] | None = None

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self.guard.content_safety is not None and (prompt := _last_user_text(request)):
            if self._prompt is None or self._prompt[0] != prompt:
                # The classifier is a blocking call to a local model: keep the event loop free.
                outcome = await asyncio.to_thread(self.guard.guard_prompt, prompt)
                self._prompt = (prompt, outcome)
                self.events.extend(outcome.events)
            outcome = self._prompt[1]
            if outcome.blocked:
                return ModelResponse(text=outcome.content, model=BLOCKED_MODEL, stop_reason="blocked")
        response = await self.inner.complete(request)
        outcome = self.guard.guard_output(response.text)
        self.events.extend(outcome.events)
        if outcome.events:
            return response.model_copy(update={"text": outcome.content})
        return response
