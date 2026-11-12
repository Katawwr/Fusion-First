"""Wrap a ModelClient so every reply passes the output guard. Tool calls still need `guard_tool_call`.

When the guard has a content classifier (`Guardrail(content_safety=...)`), every user message in the request passes
`guard_prompt` first, each classified once, and a request with a blocked message never reaches the model. A message's
keys are read as Ollama reads them, whatever their case: it is a user message when a key that reads `role` says
"user" or "human" (any case or spacing), or when it has no role. Every string in it is read, at any depth: text, dict
keys, metadata values, bytes (as UTF-8) and the fields of SDK objects; tool results are skipped. After a block, drop
that message from the history you send: while it is there, the request stays blocked. A part the classifier cannot
read (an image, audio, video, a file, a base64, URL or file source, Ollama's `images`) gets
`GuardConfig.on_classifier_error`: its bytes or address are not read, its other fields are. A request with more to
read or classify than one request may carry is refused under `on_unsafe_prompt`, before any call. Message roles are
trusted: assistant, system and tool turns are not classified, so give it only history the application produced.
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import hashlib
import numbers
import string
import types
from collections.abc import Collection, Mapping

from fusion_first.guardrail.guard import BLOCKED_TOO_LONG, NO_VERDICT, Guardrail
from fusion_first.guardrail.policy import Decision, GuardEvent, GuardOutcome
from fusion_first.guardrail.stages import TOO_LONG
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse

BLOCKED_MODEL = "fusion-guard"  # the `model` of a reply the guard wrote because it blocked the prompt
BLOCKED_UNREADABLE = "[blocked: the request has content the classifier cannot read]"
_REMEMBERED = 512  # prompt verdicts kept; the oldest is dropped first
_NODES = 100_000  # values read in one user message; a message with more is refused unread
_BUDGET = 500_000  # characters of user text not yet classified that one request may carry
_USER_ROLES = ("user", "human")
_TOOL_OUTPUT = frozenset({"tool_result", "function_call_output"})  # blocks the user did not write
# Part types that carry media, and fields whose value is media whatever the part's type (vLLM takes a part with no
# type, such as {"image_url": ...}).
_MEDIA = frozenset({"image", "image_url", "input_image", "audio", "input_audio", "video", "file", "input_file",
                    "audio_url", "video_url", "image_embeds", "audio_embeds"})
_MEDIA_FIELDS = frozenset({"image_url", "audio_url", "video_url", "input_audio", "image_embeds", "audio_embeds",
                           "image_pil", "file", "images"})
_PAYLOAD = frozenset({"data", "url", "file_data"}) | _MEDIA | _MEDIA_FIELDS  # in media: the bytes, or where they are
_OPAQUE_SOURCES = frozenset({"base64", "url", "file"})  # a `source` that holds bytes or points elsewhere
_CODE = (type, types.ModuleType, types.FunctionType, types.BuiltinFunctionType, types.MethodType)  # no text in it
# Ollama decodes a message's keys as Go's encoding/json does: ASCII case aside, U+017F reads "s" and U+212A "k".
_KEY_FOLD = str.maketrans(string.ascii_uppercase + "\u017f\u212a", string.ascii_lowercase + "sk")


def _key(key) -> str | None:
    """A message key as Ollama matches it against a field's name; None for a key that is not text."""
    return key.translate(_KEY_FOLD) if isinstance(key, str) else None


def _kind(part) -> str | None:
    kind = part.get("type") if isinstance(part, Mapping) else getattr(part, "type", None)
    return kind if isinstance(kind, str) else None


def _empty(value) -> bool:
    return value is None or (isinstance(value, str | bytes | bytearray | list | tuple | dict) and not value)


def _fields(part) -> Mapping | None:
    """An SDK object's fields: `model_dump()` (pydantic), else its dataclass fields, `__slots__` and `vars()`
    together; None when it has none."""
    dump = getattr(part, "model_dump", None)
    if callable(dump):
        try:
            fields = dump()
        except Exception:
            fields = None
        if isinstance(fields, Mapping):
            return fields
    fields = {}
    if dataclasses.is_dataclass(part):
        fields.update((f.name, getattr(part, f.name)) for f in dataclasses.fields(part) if hasattr(part, f.name))
    for cls in type(part).__mro__:
        names = cls.__dict__.get("__slots__", ())
        for name in (names,) if isinstance(names, str) else names:
            attr = f"_{cls.__name__.lstrip('_')}{name}" if name.startswith("__") and not name.endswith("__") else name
            if name not in fields and name not in ("__dict__", "__weakref__") and hasattr(part, attr):
                fields[name] = getattr(part, attr)
    fields.update((k, v) for k, v in getattr(part, "__dict__", {}).items() if k not in fields)
    return fields or None


def _children(value, media: bool, unread: list[str]) -> list[tuple[object, bool]]:
    """What `_read` reads next in `value`, in order, each with whether it sits in media. Parts the classifier cannot
    read go to `unread`."""
    if isinstance(value, enum.Enum):
        return [(value.value, media)]
    if isinstance(value, Mapping):
        fields = value
    elif isinstance(value, Collection):
        return [(item, media) for item in value]
    elif isinstance(value, _CODE) or (fields := _fields(value)) is None:
        unread.append(type(value).__name__)
        return []
    kind = _kind(fields)
    if kind in _TOOL_OUTPUT:
        return []
    if kind in _MEDIA and not media:
        unread.append(kind)
    media = media or kind in _MEDIA
    out = []
    for key, item in fields.items():
        out.append((key, media))  # a key is read like any other string
        if key in _MEDIA_FIELDS:
            if not _empty(item):
                if not media:
                    unread.append(key)
                if isinstance(item, Mapping):
                    out.append((item, True))  # its other fields are read, its bytes or address are not
        elif not (media and key in _PAYLOAD):
            opaque = key == "source" and _kind(item) in _OPAQUE_SOURCES
            if opaque and not media:
                unread.append(f"{_kind(item)} source")
            out.append((item, media or opaque))
    return out


def _read(*content) -> tuple[list[str], list[str], str]:
    """(every string in a user message's content, a short description of each part the classifier cannot read, ""
    or why the read stopped: "nodes" past `_NODES` values, "size" past `_BUDGET` characters of text).

    Iterative, with no depth limit; each container is read once, so a cycle ends and a shared part is read once.
    Every string is read: dict keys and metadata values too, bytes as UTF-8, SDK objects through their fields
    (`_fields`); tool output is skipped. Media (a media part, a media field such as vLLM's `image_url`, a base64, URL
    or file `source`) cannot be read: its bytes or address are skipped, its other fields read."""
    texts: list[str] = []
    unread: list[str] = []
    seen: dict[int, object] = {}  # every container read, kept alive so that no id is reused during the walk
    stack: list[tuple[object, bool]] = [(value, False) for value in reversed(content)]
    nodes = size = 0
    while stack:
        value, media = stack.pop()
        nodes += 1
        if nodes > _NODES:
            return texts, unread, "nodes"
        try:
            if isinstance(value, bytes | bytearray | memoryview):
                value = bytes(value).decode("utf-8", "replace")
            if isinstance(value, str):
                texts.append(value)
                size += len(value) + 1
                if size > _BUDGET:
                    return texts, unread, "size"
                continue
            if value is None or isinstance(value, numbers.Number) or id(value) in seen:
                continue
            seen[id(value)] = value
            children = _children(value, media, unread)
        except Exception:  # an object that fails when read is a part the stage cannot read
            unread.append(type(value).__name__)
            continue
        stack.extend(reversed(children))
    return texts, unread, ""


def _is_user(role) -> bool:
    """A user's role: None, or one that reads "user" or "human" whatever its case or spacing (an enum by its
    value). A role that cannot be read as text counts as one."""
    try:
        if isinstance(role, enum.Enum) and not isinstance(role, str):
            role = role.value
        return role is None or (role if isinstance(role, str) else str(role)).strip().lower() in _USER_ROLES
    except Exception:
        return True


def _user_message(message) -> tuple[str, list[str], str] | None:
    """(text, parts the stage cannot read, "" or why the read stopped) of a user message; None for another role.

    Keys are matched as Ollama matches them (`_key`). A message is the user's unless every key that reads `role`
    names another role (Ollama keeps the last such key, other providers read `role` exactly); one that is not a
    mapping has no role. Every key that reads `content` is read first, every one that reads `images` holds Ollama's
    images, and every other key is read with its value."""
    if not isinstance(message, Mapping):
        texts, unread, stopped = _read(message)
        return "\n".join(t for t in texts if t), unread, stopped
    try:
        items = list(message.items())
    except Exception:
        return "", [type(message).__name__], ""
    roles = [value for key, value in items if _key(key) == "role"]
    if roles and not any(_is_user(role) for role in roles):
        return None
    content, rest, images = [], [], 0
    for key, value in items:
        name = _key(key)
        if name == "content":
            content.append(value)
        elif name == "images":
            images += len(value) if isinstance(value, list | tuple) else int(not _empty(value))
        elif name != "role":
            rest += [key, value]
    texts, unread, stopped = _read(*content, *rest)
    return "\n".join(t for t in texts if t), ["image"] * images + unread, stopped


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

    def _refuse(self, detail: str) -> ModelResponse | None:
        """A request with more to read or classify than the stage takes: `on_unsafe_prompt`, recorded, and no call.
        The blocked reply, or None when the deployment only records (the request goes on unclassified)."""
        decision = self.guard.config.on_unsafe_prompt
        self.events.append(GuardEvent(stage="input", check="content_safety", owasp="", decision=decision,
                                      detail=f"{TOO_LONG}: {detail}"))
        if decision == Decision.BLOCK:
            return ModelResponse(text=BLOCKED_TOO_LONG, model=BLOCKED_MODEL, stop_reason="blocked")
        return None

    async def _guard_request(self, request: ModelRequest) -> ModelResponse | None:
        """The reply for a request the stage blocks, or None to send it on. Every user message is read before any is
        classified, so a request too large to read or classify costs no call."""
        messages, pending, size = [], set(), 0
        for message in request.messages:
            read = _user_message(message)
            if read is None:
                continue
            text, unread, stopped = read
            if stopped == "nodes":
                return self._refuse(f"a user message holds more than {_NODES} values")
            if text and text not in self._prompts and text not in pending:
                pending.add(text)
                size += len(text)
            if stopped == "size" or size > _BUDGET:
                return self._refuse(f"the request holds more than {_BUDGET} characters of user text not yet "
                                    "classified")
            messages.append((text, unread))
        for prompt, unread in messages:
            if prompt:
                outcome = await self._guard_prompt(prompt)
                if outcome.blocked:
                    return ModelResponse(text=outcome.content, model=BLOCKED_MODEL, stop_reason="blocked")
            if unread and self._unreadable(unread) == Decision.BLOCK:
                return ModelResponse(text=BLOCKED_UNREADABLE, model=BLOCKED_MODEL, stop_reason="blocked")
        return None

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if getattr(self.guard, "content_safety", None) is not None:
            blocked = await self._guard_request(request)
            if blocked is not None:
                return blocked
        response = await self.inner.complete(request)
        outcome = self.guard.guard_output(response.text)
        self.events.extend(outcome.events)
        if outcome.events:
            return response.model_copy(update={"text": outcome.content})
        return response
