"""Wrap a ModelClient so every reply passes the output guard. Tool calls still need `guard_tool_call`.

When the guard has a content classifier (`Guardrail(content_safety=...)`), every user message in the request passes
`guard_prompt` first, each classified once, and a request with a blocked message never reaches the model, which is
sent the client's own copy of what was read: a change made while the classifier runs does not reach it (a message
that cannot be copied is read again before it is sent, and the request is refused if it changed). A message is the
user's when any provider would send it as a user turn: when it has no `role` key (claude-cli's default), or when a key
that reads `role` as Ollama reads keys (any case) holds a role that is not text or that reads "user" or "human" on the
stage's canonical form (invisible characters dropped, look-alikes folded), as text or as it prints. Every string in it
is read, at any depth: text, dict keys, metadata values, bytes (as UTF-8), the fields of SDK objects, and how a str
subclass prints. A tool result is skipped only where a provider takes one: as one of the message's own blocks right
after the turn that made the call, once per call; any other is read. After a block, drop that
message from the history you send: while it is there, the request stays blocked. A part the classifier cannot read
(an image, audio, video, a file, a base64, URL or file source, Ollama's `images`) gets
`GuardConfig.on_classifier_error`, recorded once for each message that holds one: its bytes or address are not read,
its other fields are. A request whose user messages hold more values or characters than the reader takes is refused
under `on_unsafe_prompt` before any call; one whose new text takes more classifier calls or characters than one
request may is refused under it once what fits is classified, and what was classified is remembered, so the same
request goes further the next time. Message roles are trusted otherwise: assistant, system and tool turns are not
classified, so give it only history the application produced.
"""

from __future__ import annotations

import asyncio
import collections
import copy
import dataclasses
import enum
import hashlib
import numbers
import re
import string
import types
from collections.abc import Collection, Mapping

from fusion_first.guardrail.guard import BLOCKED_TOO_LONG, NO_VERDICT, Guardrail
from fusion_first.guardrail.policy import Decision, GuardEvent
from fusion_first.guardrail.stages import TOO_LONG, LlamaGuard, _canon
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse

BLOCKED_MODEL = "fusion-guard"  # the `model` of a reply the guard wrote because it blocked the prompt
BLOCKED_UNREADABLE = "[blocked: the request has content the classifier cannot read]"
BLOCKED_CHANGED = "[blocked: the request changed while it was classified]"
_REMEMBERED = 65_536  # verdicts kept besides those of the last request; the least recently used is dropped first
_NODES = 100_000  # values read in the user messages of one request; a request with more is refused unread
_BUDGET = 500_000  # characters of user text not yet classified that one request may carry
_CALLS = 128  # classifier calls one request may take: one per window with `LlamaGuard`, one per text otherwise
_USER_ROLES = ("user", "human")
_ROLE_CHARS = 64  # a longer role is no role a provider knows: counted as the user's, unread
_TOOL_OUTPUT = frozenset({"tool_result", "function_call_output"})  # blocks that answer a tool call
# Blocks that make a tool call. OpenAI's `tool_calls` are answered by `tool` messages, never by a user's block, and
# their ids can be guessed (this repo's tool loop numbers them), so they are not counted.
_TOOL_CALLS = frozenset({"tool_use", "server_tool_use", "mcp_tool_use", "function_call", "custom_tool_call"})
# A repr that wraps str's own (markupsafe's Markup('...'), numpy's np.str_('...')): the same text, nothing to read.
_WRAPPED = re.compile(r"[\w.]*\((.*)\)", re.DOTALL)
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
_NEW = object()  # a request's text not yet classified


def _key(key) -> str | None:
    """A message key as Ollama matches it against a field's name; None for a key that is not text."""
    return key.translate(_KEY_FOLD) if isinstance(key, str) else None


def _kind(part) -> str | None:
    kind = part.get("type") if isinstance(part, Mapping) else getattr(part, "type", None)
    return kind if isinstance(kind, str) else None


def _empty(value) -> bool:
    return value is None or (isinstance(value, str | bytes | bytearray | list | tuple | dict) and not value)


def _digest(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()


def _mark(value) -> object:
    """What tells one skipped payload from another without reading it: its hash, else its type."""
    try:
        if isinstance(value, bytearray | memoryview):
            value = bytes(value)
        elif isinstance(value, list):
            value = tuple(value)
        return hash(value)
    except Exception:
        return type(value).__name__


def _fields(part) -> Mapping | None:
    """An SDK object's fields: `model_dump()` (pydantic) with any field it leaves out (`exclude=True` still shows in
    the repr claude-cli prints), else its dataclass fields, `__slots__` and `vars()` together; None when it has
    none."""
    dump = getattr(part, "model_dump", None)
    if callable(dump):
        try:
            fields = dump()
        except Exception:
            fields = None
        if isinstance(fields, Mapping):
            return {**fields, **{k: v for k, v in getattr(part, "__dict__", {}).items() if k not in fields}}
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


def _renderings(text: str) -> list[str]:
    """A string as providers send it: its characters (json), and for a str subclass how it prints when that is other
    text (claude-cli renders a message with str(), f-strings and, inside a list, repr()). A repr that wraps str's own
    adds nothing, and a way of printing that fails is one no provider can send."""
    plain = str.__str__(text)
    out = [plain]
    if type(text) is str:
        return out
    quoted = str.__repr__(text)
    for render in (str, lambda t: format(t, ""), repr):
        try:
            shown = render(text)
        except Exception:
            continue
        if not isinstance(shown, str):
            continue
        shown = str.__str__(shown)
        wrapped = _WRAPPED.fullmatch(shown)
        if shown not in (plain, quoted) and not (wrapped and wrapped[1] == quoted) and shown not in out:
            out.append(shown)
    return out


def _as_fields(part) -> Mapping:
    return part if isinstance(part, Mapping) else _fields(part) or {}


def _answered(part, calls: set[str]) -> str | None:
    """The id of the call in `calls` that `part` answers as a tool result (`tool_use_id` of a tool_result,
    `call_id` of a function_call_output), or None."""
    fields = _as_fields(part)
    kind = _kind(fields)
    if kind not in _TOOL_OUTPUT:
        return None
    call = fields.get("tool_use_id" if kind == "tool_result" else "call_id")
    return call if isinstance(call, str) and call in calls else None


def _children(value, media: bool, unread: list[str], marks: list) -> list[tuple[object, bool]]:
    """What `_Reader.read` reads next in `value`, in order, each with whether it sits in media. Parts the classifier
    cannot read go to `unread`, and a mark for each skipped payload to `marks`."""
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
                else:
                    marks.append(_mark(item))
        elif media and key in _PAYLOAD:
            marks.append(_mark(item))
        else:
            opaque = key == "source" and _kind(item) in _OPAQUE_SOURCES
            if opaque and not media:
                unread.append(f"{_kind(item)} source")
            out.append((item, media or opaque))
    return out


class _Reader:
    """Reads the user messages of one request: the values walked are counted across the request (`_NODES`), the
    characters read within each message (`_BUDGET`)."""

    def __init__(self):
        self.nodes = 0

    def read(self, *content) -> tuple[list[str], list[str], list, str]:
        """(every string in a user message's content, a short description of each part the classifier cannot read, a
        mark for each payload skipped, "" or why the read stopped: "nodes" or "size").

        Iterative, with no depth limit; each container is read once, so a cycle ends and a shared part is read once.
        Every string is read: dict keys and metadata values too, bytes as UTF-8, SDK objects through their fields
        (`_fields`), a str subclass as it prints too (`_renderings`). Media (a media
        part, a media field such as vLLM's `image_url`, a base64, URL or file `source`) cannot be read: its bytes or
        address are skipped, its other fields read."""
        texts: list[str] = []
        unread: list[str] = []
        marks: list = []
        seen: dict[int, object] = {}  # every container read, kept alive so that no id is reused during the walk
        stack: list[tuple[object, bool]] = [(value, False) for value in reversed(content)]
        size = 0
        while stack:
            value, media = stack.pop()
            self.nodes += 1
            if self.nodes > _NODES:
                return texts, unread, marks, "nodes"
            try:
                if isinstance(value, bytes | bytearray | memoryview):
                    value = bytes(value).decode("utf-8", "replace")
                if isinstance(value, str):
                    shown = _renderings(value)
                    texts += shown
                    size += sum(len(t) + 1 for t in shown)
                    if size > _BUDGET:
                        return texts, unread, marks, "size"
                    continue
                if value is None or isinstance(value, numbers.Number) or id(value) in seen:
                    continue
                seen[id(value)] = value
                children = _children(value, media, unread, marks)
            except Exception:  # an object that fails when read is a part the stage cannot read
                unread.append(type(value).__name__)
                continue
            stack.extend(reversed(children))
        return texts, unread, marks, ""


def _is_user(role) -> bool:
    """A user's role: None, one that is not text (an enum by its value) or longer than `_ROLE_CHARS`, or one that reads
    "user" or "human" as its characters or as it prints, matched on the stage's canonical form (case, spacing and
    invisible characters aside, look-alikes folded: claude-cli prints any role as the turn's label). A role that
    cannot be read counts as one."""
    try:
        if isinstance(role, enum.Enum) and not isinstance(role, str):
            role = role.value
        if not isinstance(role, str) or len(role) > _ROLE_CHARS:
            return True
        return any("".join(map(_canon, name)).strip().lower() in _USER_ROLES for name in _renderings(role))
    except Exception:
        return True


def _is_users(items: list[tuple]) -> bool:
    """Whether any provider sends a message with these keys as a user turn: claude-cli when it has no `role` key
    (it reads only that key), Ollama when a key that reads `role` in any case names the user, others when `role`
    does."""
    if not any(isinstance(key, str) and key == "role" for key, _ in items):
        return True
    return any(_is_user(value) for key, value in items if _key(key) == "role")


def _results_skipped(blocks, calls: set[str], answered: set[str]) -> list:
    """`blocks` without the tool results that answer `calls`, each call once: what a provider takes as the tools'
    output, not the user's text. The ids answered go to `answered`."""
    kept = []
    for block in blocks:
        try:
            call = _answered(block, calls - answered)
        except Exception:
            call = None
        if call is None:
            kept.append(block)
        else:
            answered.add(call)
    return kept


def _user_message(message, reader: _Reader, calls: set[str] | None = None,
                  answered: set[str] | None = None) -> tuple[str, list[str], list, str] | None:
    """(text, parts the stage cannot read, marks of skipped payloads, "" or why the read stopped) of a user message;
    None for another role (`_is_users`). One that is not a mapping has no role. Keys are matched as Ollama matches
    them (`_key`): every key that reads `content` is read first, every one that reads `images` holds Ollama's images,
    and every other key is read with its value. Of the blocks under the `content` key itself, a tool result that
    answers one of `calls` (the calls the turn just before made, not answered yet) is skipped, once per call; any
    other tool result is read."""
    if not isinstance(message, Mapping):
        texts, unread, marks, stopped = reader.read(message)
        return "\n".join(t for t in texts if t), unread, marks, stopped
    try:
        items = list(message.items())
    except Exception:
        return "", [type(message).__name__], [], ""
    if not _is_users(items):
        return None
    content, rest, images, marks = [], [], 0, []
    for key, value in items:
        name = _key(key)
        if name == "content":
            if calls and isinstance(key, str) and key == "content" and isinstance(value, list | tuple):
                value = _results_skipped(value, calls, set() if answered is None else answered)
            content.append(value)
        elif name == "images":
            images += len(value) if isinstance(value, list | tuple) else int(not _empty(value))
            marks.append(_mark(value))
        elif name != "role":
            rest += [key, value]
    texts, unread, more, stopped = reader.read(*content, *rest)
    return "\n".join(t for t in texts if t), ["image"] * images + unread, marks + more, stopped


def _listed(value) -> list:
    return list(value) if isinstance(value, list | tuple) else []


def _tool_calls(message) -> set[str]:
    """The ids of the tool calls a turn that is not the user's makes: the tool_use and function_call blocks under its
    `content` key (`_TOOL_CALLS`). Empty for the user's turn or one that cannot be read."""
    ids: set[str] = set()
    try:
        if not isinstance(message, Mapping) or _is_users(list(message.items())):
            return ids
        for part in _listed(message.get("content")):
            fields = _as_fields(part)
            if _kind(fields) in _TOOL_CALLS:
                ids.update(v for v in (fields.get("id"), fields.get("call_id")) if isinstance(v, str))
    except Exception:
        return set()
    return ids


def _with_copies(request: ModelRequest, users: set[int]) -> tuple[ModelRequest, list[int]]:
    """(the request with its own copy of every message, the positions of those that could not be copied). A user
    message is copied whole, so the model is sent what was read whatever the caller changes while the classifier
    runs; another is copied at its top level only, so that its role stays as read (its content is not classified)."""
    messages, fragile = [], []
    for i, message in enumerate(request.messages):
        try:
            messages.append(copy.deepcopy(message) if i in users else copy.copy(message))
        except Exception:
            messages.append(message)
            fragile.append(i)
    return request.model_copy(update={"messages": messages}), fragile


def _policy(guard, config=None) -> tuple:
    """What turns a prompt into a decision: the guard, its classifier and the settings that act on a verdict (the
    guard's own, or `config`)."""
    config = guard.config if config is None else config
    return (guard, guard.content_safety, config.on_unsafe_prompt, tuple(config.content_safety_flag_only),
            config.on_classifier_error)


def _same_policy(a: tuple | None, b: tuple | None) -> bool:
    return a is not None and b is not None and a[0] is b[0] and a[1] is b[1] and a[2:] == b[2:]


def _frozen(guard):
    """The guard with its own copy of its settings, so a change made while it classifies does not decide that
    prompt."""
    try:
        frozen = copy.copy(guard)
        frozen.config = guard.config.model_copy(deep=True)
        return frozen
    except Exception:
        return guard


class GuardedModelClient:
    def __init__(self, inner: ModelClient, guard: Guardrail):
        self.inner = inner
        self.guard = guard
        self.events: list[GuardEvent] = []
        # Verdicts by the prompt's digest (a conversation resends its earlier messages with every request): the reply
        # of a blocked prompt, or None for one that goes on.
        self._prompts: collections.OrderedDict[bytes, str | None] = collections.OrderedDict()
        self._recorded: collections.OrderedDict[bytes, None] = collections.OrderedDict()  # messages with unread parts
        self._running: dict[bytes, asyncio.Task] = {}  # prompts being classified
        self._policy: tuple | None = None
        self._keep = 0  # prompts of the last request, never dropped while it runs

    def _settle(self) -> None:
        """Forget every verdict when the guard, its classifier or the settings that turn a verdict into a decision
        changed since the last request."""
        now = _policy(self.guard)
        if not _same_policy(now, self._policy):
            self._prompts.clear()
            self._recorded.clear()
            self._running = {}
            self._policy = now

    def _remember(self, key: bytes, reply: str | None) -> None:
        self._prompts[key] = reply
        self._prompts.move_to_end(key)
        while len(self._prompts) > max(_REMEMBERED, self._keep):
            self._prompts.popitem(last=False)

    async def _guard_prompt(self, key: bytes, prompt: str) -> str | None:
        """The reply for a blocked prompt, or None. A prompt being classified for another request is awaited, not
        asked again."""
        if key in self._prompts:  # classified meanwhile, for another request
            return self._prompts[key]
        loop = asyncio.get_running_loop()
        task = self._running.get(key)
        if task is None or task.get_loop() is not loop:
            task = loop.create_task(self._classify(key, prompt, self._running))
            self._running[key] = task
        return await asyncio.shield(task)

    async def _classify(self, key: bytes, prompt: str, running: dict[bytes, asyncio.Task]) -> str | None:
        """Classify with a copy of the guard's settings taken now, and keep the verdict only while those are still the
        guard's settings: a change made meanwhile decides nothing."""
        live, me = self.guard, asyncio.current_task()
        guard = _frozen(live)
        decided_by = _policy(live, guard.config)
        try:
            # The classifier is a blocking call to a local model: keep the event loop free.
            outcome = await asyncio.to_thread(guard.guard_prompt, prompt)
        finally:  # also when a closed loop's pending task is collected, with no loop running
            if running.get(key) is me:
                del running[key]
        self.events.extend(outcome.events)
        reply = outcome.content if outcome.blocked else None
        # An outage is tried again.
        if (running is self._running and _same_policy(decided_by, _policy(self.guard))
                and not any(e.detail.startswith(NO_VERDICT) for e in outcome.events)):
            self._remember(key, reply)
        return reply

    def _unreadable(self, parts: list[str], mark: bytes) -> Decision:
        """The policy for parts the classifier cannot read, recorded once for each message that holds them: a message
        the history resends is not recorded again."""
        decision = self.guard.config.on_classifier_error
        if mark not in self._recorded:
            self._recorded[mark] = None
            while len(self._recorded) > _REMEMBERED:
                self._recorded.popitem(last=False)
            self.events.append(GuardEvent(
                stage="input", check="content_safety", owasp="", decision=decision,
                detail=f"{NO_VERDICT}: a user message holds {len(parts)} part(s) the stage cannot read "
                       f"({', '.join(sorted(set(parts)))})"))
        return decision

    def _refuse(self, detail: str, reply: str = BLOCKED_TOO_LONG) -> ModelResponse | None:
        """A request the stage does not pass as it is: `on_unsafe_prompt`, recorded. The blocked reply, or None when
        the deployment only records (the request goes on as it is)."""
        decision = self.guard.config.on_unsafe_prompt
        self.events.append(GuardEvent(stage="input", check="content_safety", owasp="", decision=decision,
                                      detail=detail))
        if decision == Decision.BLOCK:
            return ModelResponse(text=reply, model=BLOCKED_MODEL, stop_reason="blocked")
        return None

    async def _guard_request(self, request: ModelRequest) -> tuple[ModelRequest, ModelResponse | None]:
        """(the request to send, the reply when the stage blocks it). Every user message is read within the request's
        limits before anything is copied or classified. New texts are then classified in order while the request's
        budget lasts (characters, classifier calls); past it the request is refused, and what was classified is
        remembered, so the same request goes further the next time."""
        self._settle()
        classifier = self.guard.content_safety
        cost = classifier.calls if isinstance(classifier, LlamaGuard) else (lambda text: 1)
        reader = _Reader()
        verdicts: dict[bytes, object] = {}  # this request's: those remembered, then those classified
        users, reads, answerable, answered = [], [], [], set()
        for i, message in enumerate(request.messages):
            # A tool result counts as one only right after the turn that made the call, and once per call.
            answerable.append(_tool_calls(request.messages[i - 1]) - answered if i else set())
            read = _user_message(message, reader, answerable[i], answered)
            reads.append(read)
            if read is None:
                continue
            text, unread, marks, stopped = read
            if stopped == "nodes":
                return request, self._refuse(f"{TOO_LONG}: the request's user messages hold more than {_NODES} "
                                             "values")
            if stopped == "size":
                return request, self._refuse(f"{TOO_LONG}: a user message holds more than {_BUDGET} characters")
            key = _digest(text) if text else None
            if key is not None and key not in verdicts:
                if key in self._prompts:
                    self._prompts.move_to_end(key)
                    verdicts[key] = self._prompts[key]
                else:
                    verdicts[key] = _NEW
            users.append((key, text, unread, marks))
        sent, fragile = _with_copies(request, {i for i, read in enumerate(reads) if read is not None})
        self._keep = len(verdicts)
        size = calls = 0
        for key, text, unread, marks in users:
            if key is not None:
                reply = verdicts[key]
                if reply is _NEW:
                    size, calls = size + len(text), calls + cost(text)
                    if size > _BUDGET:
                        return sent, self._refuse(f"{TOO_LONG}: the request holds more than {_BUDGET} characters of "
                                                  "user text not yet classified")
                    if calls > _CALLS:
                        return sent, self._refuse(f"{TOO_LONG}: the user text not yet classified takes more than "
                                                  f"{_CALLS} classifier calls")
                    reply = verdicts[key] = await self._guard_prompt(key, text)
                if reply is not None:
                    return sent, ModelResponse(text=reply, model=BLOCKED_MODEL, stop_reason="blocked")
            if unread and self._unreadable(unread, _digest(repr((key, sorted(unread), marks)))) == Decision.BLOCK:
                return sent, ModelResponse(text=BLOCKED_UNREADABLE, model=BLOCKED_MODEL, stop_reason="blocked")
        # A message that could not be copied is sent as the caller's own object: it must still read as it did.
        again = _Reader()
        if any(_user_message(request.messages[i], again, answerable[i]) != reads[i] for i in fragile):
            return sent, self._refuse("content classifier: a user message changed while it was classified",
                                      BLOCKED_CHANGED)
        return sent, None

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if getattr(self.guard, "content_safety", None) is not None:
            request, blocked = await self._guard_request(request)
            if blocked is not None:
                return blocked
        response = await self.inner.complete(request)
        outcome = self.guard.guard_output(response.text)
        self.events.extend(outcome.events)
        if outcome.events:
            return response.model_copy(update={"text": outcome.content})
        return response
