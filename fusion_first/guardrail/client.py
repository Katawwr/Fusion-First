"""Wrap a ModelClient so every reply passes the output guard. Tool calls still need `guard_tool_call`.

When the guard has a content classifier (`Guardrail(content_safety=...)`), every user message in the request
passes `guard_prompt` first, each classified once, and a request with a blocked message never reaches the model.
After a block, drop that message from the history you send: while it is there, the request stays blocked.
"""

from __future__ import annotations

import asyncio

from fusion_first.guardrail.guard import NO_VERDICT, Guardrail
from fusion_first.guardrail.policy import GuardEvent, GuardOutcome
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse

BLOCKED_MODEL = "fusion-guard"  # the `model` of a reply the guard wrote because it blocked the prompt
_REMEMBERED = 512  # prompt verdicts kept; the oldest is dropped first


def _text(content) -> str:
    """A message's text: the string itself, or the text parts of a structured message."""
    if isinstance(content, str):
        return content
    if isinstance(content, list | tuple):
        parts = [p if isinstance(p, str) else str(p.get("text") or "") for p in content if isinstance(p, str | dict)]
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _user_texts(request: ModelRequest) -> list[str]:
    """The text of every user message in the request, in order. Checking the last one alone would let a later
    "please continue" carry an earlier request past the stage."""
    return [text for m in request.messages
            if isinstance(m, dict) and m.get("role") == "user" and (text := _text(m.get("content")))]


class GuardedModelClient:
    def __init__(self, inner: ModelClient, guard: Guardrail):
        self.inner = inner
        self.guard = guard
        self.events: list[GuardEvent] = []
        # Verdicts by prompt text: a conversation resends its earlier messages with every request.
        self._prompts: dict[str, GuardOutcome] = {}

    async def _guard_prompt(self, prompt: str) -> GuardOutcome:
        outcome = self._prompts.get(prompt)
        if outcome is None:
            # The classifier is a blocking call to a local model: keep the event loop free.
            outcome = await asyncio.to_thread(self.guard.guard_prompt, prompt)
            self.events.extend(outcome.events)
            if not any(e.detail.startswith(NO_VERDICT) for e in outcome.events):  # a failure is tried again
                if len(self._prompts) >= _REMEMBERED:
                    del self._prompts[next(iter(self._prompts))]
                self._prompts[prompt] = outcome
        return outcome

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self.guard.content_safety is not None:
            for prompt in _user_texts(request):
                outcome = await self._guard_prompt(prompt)
                if outcome.blocked:
                    return ModelResponse(text=outcome.content, model=BLOCKED_MODEL, stop_reason="blocked")
        response = await self.inner.complete(request)
        outcome = self.guard.guard_output(response.text)
        self.events.extend(outcome.events)
        if outcome.events:
            return response.model_copy(update={"text": outcome.content})
        return response
