"""Wrap a ModelClient so every reply passes the output guard. Tool calls still need `guard_tool_call`.

When the guard has a content classifier (`Guardrail(content_safety=...)`), every user message in the request
passes `guard_prompt` first, each classified once, and a request with a blocked message never reaches the model.
After a block, drop that message from the history you send: while it is there, the request stays blocked. A part of
a user message the classifier cannot read (an image, an unknown block) gets `GuardConfig.on_classifier_error`.
"""

from __future__ import annotations

import asyncio
import hashlib

from fusion_first.guardrail.guard import NO_VERDICT, Guardrail
from fusion_first.guardrail.policy import Decision, GuardEvent, GuardOutcome
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse

BLOCKED_MODEL = "fusion-guard"  # the `model` of a reply the guard wrote because it blocked the prompt
BLOCKED_UNREADABLE = "[blocked: the request has content the classifier cannot read]"
_REMEMBERED = 512  # prompt verdicts kept; the oldest is dropped first
_DEPTH = 8  # nesting read in a structured message
# Blocks a user message carries that the user did not write: tool output and the model's own turns.
_NOT_THE_USERS = frozenset({"tool_result", "tool_use", "function_call", "function_call_output", "thinking",
                            "redacted_thinking", "server_tool_use", "web_search_tool_result"})


def _field(part, name: str):
    return part.get(name) if isinstance(part, dict) else getattr(part, name, None)


def _read(content, depth: int = 0) -> tuple[list[str], list[str]]:
    """(the texts of a message's content, a short description of each part it holds that is not text): a string,
    a list of parts, a dict or SDK object with `text`, a text document, nested `content`."""
    if content is None:
        return [], []
    if isinstance(content, str):
        return [content], []
    if depth > _DEPTH:
        return [], ["nesting deeper than the stage reads"]
    if isinstance(content, list | tuple):
        texts, unread = [], []
        for part in content:
            t, u = _read(part, depth + 1)
            texts += t
            unread += u
        return texts, unread
    kind = _field(content, "type")
    if kind in _NOT_THE_USERS:
        return [], []
    text = _field(content, "text")
    if isinstance(text, str):
        return [text], []
    source = _field(content, "source")
    if kind == "document" and _field(source, "type") == "text" and isinstance(_field(source, "data"), str):
        return [_field(source, "data")], []
    nested = _field(content, "content")
    if isinstance(nested, str | list | tuple):
        return _read(nested, depth + 1)
    return [], [str(kind or type(content).__name__)]


def _user_messages(request: ModelRequest) -> list[tuple[str, list[str]]]:
    """(text, parts the stage cannot read) of every user message in the request, in order. Checking the last one
    alone would let a later "please continue" carry an earlier request past the stage."""
    out = []
    for m in request.messages:
        if isinstance(m, dict) and m.get("role") == "user":
            texts, unread = _read(m.get("content"))
            out.append(("\n".join(t for t in texts if t), unread))
    return out


class GuardedModelClient:
    def __init__(self, inner: ModelClient, guard: Guardrail):
        self.inner = inner
        self.guard = guard
        self.events: list[GuardEvent] = []
        # Verdicts by prompt text: a conversation resends its earlier messages with every request.
        self._prompts: dict[str, GuardOutcome] = {}
        self._unread: set[str] = set()  # parts already recorded as unreadable

    def _remember(self, prompt: str, outcome: GuardOutcome) -> None:
        if len(self._prompts) >= _REMEMBERED:
            self._prompts.pop(next(iter(self._prompts)), None)
        self._prompts[prompt] = outcome

    async def _guard_prompt(self, prompt: str) -> GuardOutcome:
        outcome = self._prompts.get(prompt)
        if outcome is None:
            # The classifier is a blocking call to a local model: keep the event loop free.
            outcome = await asyncio.to_thread(self.guard.guard_prompt, prompt)
            self.events.extend(outcome.events)
            if not any(e.detail.startswith(NO_VERDICT) for e in outcome.events):  # an outage is tried again
                self._remember(prompt, outcome)
        return outcome

    def _unreadable(self, parts: list[str]) -> Decision:
        """The policy for parts the classifier cannot read, recorded once per kind of part."""
        decision = self.guard.config.on_classifier_error
        key = hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()
        if key not in self._unread:
            self._unread.add(key)
            self.events.append(GuardEvent(
                stage="input", check="content_safety", owasp="", decision=decision,
                detail=f"{NO_VERDICT}: a user message holds {len(parts)} part(s) the stage cannot read "
                       f"({', '.join(sorted(set(parts)))})"))
        return decision

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if getattr(self.guard, "content_safety", None) is not None:
            for prompt, unread in _user_messages(request):
                if prompt:
                    outcome = await self._guard_prompt(prompt)
                    if outcome.blocked:
                        return ModelResponse(text=outcome.content, model=BLOCKED_MODEL, stop_reason="blocked")
                if unread and self._unreadable(unread) == Decision.BLOCK:
                    return ModelResponse(text=BLOCKED_UNREADABLE, model=BLOCKED_MODEL, stop_reason="blocked")
        response = await self.inner.complete(request)
        outcome = self.guard.guard_output(response.text)
        self.events.extend(outcome.events)
        if outcome.events:
            return response.model_copy(update={"text": outcome.content})
        return response
