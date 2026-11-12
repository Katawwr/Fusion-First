"""Wrap a ModelClient so every reply passes the output guard. Tool calls still need `guard_tool_call`.

When the guard has a content classifier (`Guardrail(content_safety=...)`), every user message in the request (role
"user" or "human", whatever its case or spacing) passes `guard_prompt` first, each classified once, and a request
with a blocked message never reaches the model. Every text field of the message is read, at any depth; tool results
are skipped. After a block, drop that message from the history you send: while it is there, the request stays
blocked. A part the classifier cannot read (an image, audio, a file, a base64, URL or file source, Ollama's `images`)
gets `GuardConfig.on_classifier_error`. Message roles are trusted: assistant, system and tool turns are not
classified, so give it only history the application produced.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping

from fusion_first.guardrail.guard import NO_VERDICT, Guardrail
from fusion_first.guardrail.policy import Decision, GuardEvent, GuardOutcome
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse

BLOCKED_MODEL = "fusion-guard"  # the `model` of a reply the guard wrote because it blocked the prompt
BLOCKED_UNREADABLE = "[blocked: the request has content the classifier cannot read]"
_REMEMBERED = 512  # prompt verdicts kept; the oldest is dropped first
_DEPTH = 8  # nesting read in a structured message
_USER_ROLES = ("user", "human")
_TOOL_OUTPUT = frozenset({"tool_result", "function_call_output"})  # blocks the user did not write
_MEDIA = frozenset({"image", "image_url", "input_image", "audio", "input_audio", "video", "file", "input_file"})
_OPAQUE_SOURCES = frozenset({"base64", "url", "file"})  # a `source` that holds bytes or points elsewhere
# Fields that describe a part rather than say something: never classified.
_METADATA = frozenset({"type", "id", "tool_use_id", "media_type", "mime_type", "cache_control", "format", "detail",
                       "signature", "citations"})
_MESSAGE_METADATA = frozenset({"role", "content", "tool_call_id", "id", "cache_control"})  # `content` is read first


def _kind(part) -> str | None:
    kind = part.get("type") if isinstance(part, Mapping) else getattr(part, "type", None)
    return kind if isinstance(kind, str) else None


def _fields(part) -> Mapping | None:
    """A part's fields: a mapping as it is, an SDK object through `model_dump()` or `vars()`; None for neither."""
    if isinstance(part, Mapping):
        return part
    dump = getattr(part, "model_dump", None)
    if callable(dump):
        fields = dump()
        return fields if isinstance(fields, Mapping) else None
    try:
        return vars(part)
    except TypeError:
        return None


def _read(content, depth: int = 0) -> tuple[list[str], list[str]]:
    """(the texts in a message's content, a short description of each part the classifier cannot read). Every string
    field is read, in lists and mappings at any depth up to `_DEPTH`, except metadata fields and tool output; media
    and a base64, URL or file `source` cannot be read (the block's other fields still are)."""
    if content is None or isinstance(content, bool | int | float):
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
    fields = _fields(content)
    if fields is None:
        return [], [type(content).__name__]
    kind = _kind(fields)
    if kind in _TOOL_OUTPUT:
        return [], []
    if kind in _MEDIA:
        return [], [kind]
    texts, unread = [], []
    for key, value in fields.items():
        if key in _METADATA:
            continue
        if key == "source" and (source := _kind(value)) in _OPAQUE_SOURCES:
            unread.append(f"{source} source")
            continue
        t, u = _read(value, depth + 1)
        texts += t
        unread += u
    return texts, unread


def _is_user(role) -> bool:
    """A user turn, whatever the case or spacing of its role ("User", " user", "human"); a str enum by its value."""
    return (role if isinstance(role, str) else str(role)).strip().lower() in _USER_ROLES


def _user_messages(request: ModelRequest) -> list[tuple[str, list[str]]]:
    """(text, parts the stage cannot read) of every user message in the request, in order: its content and every
    other key but metadata (Ollama's `images`: one unreadable part per image). Checking the last one alone would let
    a later "please continue" carry an earlier request past the stage."""
    out = []
    for m in request.messages:
        if not (isinstance(m, dict) and _is_user(m.get("role"))):
            continue
        texts, unread = _read(m.get("content"))
        for key, value in m.items():
            if key == "images":  # Ollama's own field for a vision model's images
                images = value if isinstance(value, list | tuple) else [value] if value else []
                unread += ["image"] * len(images)
            elif key not in _MESSAGE_METADATA:
                t, u = _read(value)
                texts += t
                unread += u
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
