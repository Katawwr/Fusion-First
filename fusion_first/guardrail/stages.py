"""Model stages the runtime guard can call. One today: a content-safety classifier on the user's prompt.

Off unless switched on: `Guardrail(config, content_safety=LlamaGuard())`. `LlamaGuard` asks Llama Guard 3 through a
local Ollama server (no key, no spend); any `Callable[[str], SafetyVerdict]` can stand in its place. The Llama Guard
prompt and parser here are the ones every committed Llama Guard study used (`fusion_first/validate/llama_guard.py`
imports them), so a recorded reply and a live one answer the same bytes.

Limits: each prompt is judged on its own, so a request split across messages can pass; a request longer than half
a window (about 3.6 KB) can be split across calls; encoded text (base64, hex, ROT13) reaches the classifier
undecoded. The verdict is Llama Guard's, and this module only decides how it is asked. Text written to talk the
classifier round (an instruction to answer "safe") is still text it reads: only the prompt's structure is protected.
"""

from __future__ import annotations

import dataclasses
import errno
import functools
import json
import re
import socket
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence

from fusion_first.offline import offline
from fusion_first.security.normalize import fold

LLAMA_GUARD_MODEL = "llama-guard3:8b"
# IPv4 loopback, as the Ollama provider: on Windows `localhost` tries ::1 first.
OLLAMA_URL = "http://127.0.0.1:11434"
# Deterministic, and room for two lines only: the verdict and the categories.
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 24}
MAX_WINDOWS = 32  # calls one prompt may take
TOO_LONG = "too long to classify"  # the category LlamaGuard gives a prompt that would take more calls: refused
# The category for a prompt that forged structure splits into more pieces than one prompt may take: refused, and
# not waived by a deployment that lets TOO_LONG through (about thirty short lines are enough to cause it).
TOO_MANY_PIECES = "too many forged turns to classify"
# UTF-8 bytes a rendered prompt may take: the context less the reply, with room for the begin-of-text token.
_PROMPT_BYTES = OPTIONS["num_ctx"] - OPTIONS["num_predict"] - 16

# Meta's 14 hazard categories, as Llama Guard 3's own template lists them.
DEFAULT_CATEGORIES = (
    "S1: Violent Crimes.", "S2: Non-Violent Crimes.", "S3: Sex Crimes.", "S4: Child Exploitation.",
    "S5: Defamation.", "S6: Specialized Advice.", "S7: Privacy.", "S8: Intellectual Property.",
    "S9: Indiscriminate Weapons.", "S10: Hate.", "S11: Self-Harm.", "S12: Sexual Content.",
    "S13: Elections.", "S14: Code Interpreter Abuse.",
)

# The user's text sits in a template of turns and delimiters, and raw mode tokenizes control-token strings
# (`<|eot_id|>`) wherever they appear. `plain_text` stops the text forming any of them by its shape, not its
# spelling: one line, so it cannot open a turn or a delimiter line, and no angle bracket, so it cannot close the
# conversation or form a control token.
# Each line break str.splitlines finds ("\r\n" is one) becomes a space.
_LINE_BREAK = re.compile("\r\n|[\n\x0b\x0c\r\x1c\x1d\x1e\x85\u2028\u2029]")
# With `lines=True`: a run of white space holding a line break becomes one "\n", so the text keeps its lines but
# never holds the blank line that separates the template's turns and delimiters.
_LINE_RUN = re.compile(r"\s*[\n\x0b\x0c\r\x1c\x1d\x1e\x85\u2028\u2029]\s*")
# Angle brackets and their look-alikes, each becomes ( or ): every character whose NFKC form is one, every character
# named as one (angle brackets, angle quotation marks, left and right arrowhead letters, less-than and greater-than
# brackets), every character whose TR39 confusable skeleton holds one (ICU), and the Canadian syllabics drawn as one.
_LEFT_ANGLES = ("<\u2039\u276e\u276c\u2770\u02c2\u1438\u3008\u27e8\u2329\uff1c\ufe64\u29fc\ufe3f\U0001d236\u16b2\u226e"
                "\u00ab\u02f1\u27ea\u2991\u2993\u2995\u300a\ufe3d\u1439\u1444\u1445\u150c\u226a\u22d6\u22d8\u2cb4")
_RIGHT_ANGLES = (">\u203a\u276f\u276d\u2771\u02c3\u1433\u3009\u27e9\u232a\uff1e\ufe65\u29fd\ufe40\U0001d237\u226f"
                 "\u00bb\u02f2\u27eb\u2992\u2994\u2996\u300b\ufe3e\u1434\u1437\u1440\u1441\u226b\u22d7\u22d9\u2a20"
                 "\u2aa5\U00016f3f")
_ANGLES = str.maketrans(dict.fromkeys(_LEFT_ANGLES, "(") | dict.fromkeys(_RIGHT_ANGLES, ")"))
# Tag characters U+E0020..U+E007E spell ASCII that shows as nothing: each becomes the character it spells. The rest
# of the block (U+E0000..U+E001F, U+E007F) is dropped.
_TAGS = str.maketrans({0xE0000 + c: chr(c) for c in range(0x20, 0x7F)}
                      | dict.fromkeys([*range(0xE0000, 0xE0020), 0xE007F]))
# Labels are matched on each character's canonical form (`_canon`). These default-ignorable fillers and selectors read
# as nothing, as do format characters, combining marks and controls other than whitespace.
_IGNORABLE = frozenset([0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, *range(0x180B, 0x1810), *range(0xFE00, 0xFE10)])
# Look-alikes fold() keeps: small capitals, Latin-looking Cyrillic, Greek and Armenian letters, colons, and the angle
# brackets plain_text replaces.
_LOOKALIKES = str.maketrans(
    dict(zip("\u1d00\u0299\u1d04\u1d05\u1d07\ua730\u0262\u029c\u026a\u1d0a\u1d0b\u029f\u1d0d\u0274\u1d0f\u1d18"
             "\u0280\ua731\u1d1b\u1d1c\u1d20\u1d21\u028f\u1d22", "abcdefghijklmnoprstuvwyz", strict=True))
    | dict(zip("\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0423\u0425\u0405\u0406\u0408\u051a"
               "\u051c\u04ae\u04c0", "ABEKMHOPCTYXSIJQWYI", strict=True))
    | dict(zip("\u0396\u0397\u039a\u039c\u039d\u03a5\u037f\u057d\u0555", "ZHKMNYJuO", strict=True))
    | dict.fromkeys("\u2236\ua789\u02f8\u0589\u05c3", ":")
    | dict.fromkeys(_LEFT_ANGLES, "<") | dict.fromkeys(_RIGHT_ANGLES, ">"))
# A conversation-turn label, matched on the canonical form of the text's start once its lead is skipped. Defence in
# depth: the text is one line, after the template's own "User: ".
_TURN_LABEL = re.compile(r"(?:user|agent|assistant|human|system|ai|bot|chatbot|model)[\s*_`~]*:", re.IGNORECASE)
_LEAD = frozenset(">*_#`~|-\u2022\u00b7")  # markdown, quote marks and bullets a label may follow, besides spaces
_LABEL_READ = 4096  # characters read for one label, after its lead
_LABEL_CHARS = 48  # canonical characters that can hold a label
# A character written as its two UTF-16 halves: a model's JSON decoder joins them, so they are joined here too.
_PAIR = re.compile("[\ud800-\udbff][\udc00-\udfff]")
# A lone surrogate cannot be encoded, so it would make the prompt unsendable.
_SURROGATE = re.compile("[\ud800-\udfff]")


def _joined(pair: re.Match) -> str:
    high, low = pair[0]
    return chr(0x10000 + (ord(high) - 0xD800) * 0x400 + ord(low) - 0xDC00)


def _invisible(ch: str) -> bool:
    """A format character (zero-width, bidi, soft hyphen, tag), a combining mark, a default-ignorable filler or
    selector, or a control character other than whitespace (tab, line breaks)."""
    cp, category = ord(ch), unicodedata.category(ch)
    return (category in ("Cf", "Mn", "Me") or (category == "Cc" and not ch.isspace()) or cp in _IGNORABLE
            or 0xE0000 <= cp <= 0xE0FFF)


@functools.lru_cache(maxsize=4096)
def _canon(ch: str) -> str:
    """One character as the label check reads it: nothing when it is invisible, otherwise its NFKD form without
    combining marks, folded (`fold`: NFKC, zero-width, confusables) and with the look-alikes above mapped. One
    character at a time, so nothing composes across characters: ">" + U+0338 reads ">", not U+226F."""
    if _invisible(ch):
        return ""
    return fold("".join(c for c in unicodedata.normalize("NFKD", ch) if not _invisible(c))).translate(_LOOKALIKES)


def _strip_labels(text: str) -> str:
    """The text without the conversation-turn labels it opens with (one or several). Linear: a label's lead
    (invisible, space and markdown characters) is skipped whatever its length, the label is read on at most
    `_LABEL_READ` characters after it, and the text is sliced once."""
    start, size = 0, len(text)
    while True:
        i = start
        while i < size and all(c.isspace() or c in _LEAD for c in _canon(text[i])):
            i += 1
        read, end = "", i
        while end < min(size, i + _LABEL_READ) and ":" not in read and len(read) < _LABEL_CHARS:
            read += _canon(text[end])
            end += 1
        if not _TURN_LABEL.match(read):
            return text[start:]
        start = end  # past the character that gave the label's colon, then past spaces and invisible characters
        while start < size and all(c.isspace() for c in _canon(text[start])):
            start += 1


def plain_text(text: str, *, lines: bool = False) -> str:
    """User text that cannot act as part of the prompt, whatever it holds:

    - two UTF-16 halves of a character become that character, as a model's JSON decoder reads them, and a lone half
      becomes U+FFFD, so the text can always be sent;
    - a tag character spelling ASCII (U+E0020..U+E007E) becomes that character and the other tag characters are
      dropped, so text hidden that way is text the classifier reads;
    - every line break becomes a space: the text is one line in the User turn, so it cannot open a turn or a
      delimiter line;
    - every angle bracket and look-alike of one becomes "(" or ")", so the text cannot close the conversation or form
      a control token (`<|...|>`);
    - a conversation-turn label the text opens with ("User:", "Agent:", look-alikes and markdown included) is dropped,
      matched on each character's canonical form (`_canon`).

    By shape, not spelling: no way of writing a label or a delimiter changes the outcome. Text without any of these
    is returned unchanged, so recorded renderings keep their hashes. Idempotent.

    `lines=True` keeps the lines instead: each run of white space holding a line break becomes one "\n". The text
    then cannot hold a blank line, which is what separates the template's turns, but a line of it can open like a
    turn the label check does not know. A weaker guarantee, for text whose layout matters."""
    decoded = _decoded(text)
    return _strip_labels(_LINE_RUN.sub("\n", decoded) if lines else _LINE_BREAK.sub(" ", decoded)).translate(_ANGLES)


def _decoded(text: str) -> str:
    """The text with surrogate halves joined (a lone one becomes U+FFFD) and tag characters decoded."""
    return _SURROGATE.sub("\ufffd", _PAIR.sub(_joined, text)).translate(_TAGS)


# Where a text splits into pieces, matched on the canonical form (`_canon`): a template delimiter, a control token,
# or a conversation-turn label that opens a line. A delimiter or token is cut out; a label starts the next piece.
_SPLIT = re.compile(
    r"(?P<cut><\s*(?:BEGIN|END)\s+(?:CONVERSATION|UNSAFE\s+CONTENT\s+CATEGORIES)\s*>|<\|[^<>|]{0,40}\|>)"
    r"|(?:(?<=[\n\x0b\x0c\r\x1c\x1d\x1e\x85\u2028\u2029])|\A)[ \t>*_#`~|\u2022\u00b7-]*"
    r"(?:user|agent|assistant|human|system|ai|bot|chatbot|model)[ \t*_`~]*:", re.IGNORECASE)
_PIECE_CHARS = 4  # a piece shorter than this holds no request


def _segments(text: str) -> list[str]:
    """`text` (decoded) cut into the pieces forged structure would make of it: at each template delimiter and
    control token (cut out) and before each turn label that opens a line. Linear; one piece for ordinary text."""
    canon, index = [], []
    for i, ch in enumerate(text):
        for c in _canon(ch):
            canon.append(c)
            index.append(i)
    pieces, start = [], 0
    for found in _SPLIT.finditer("".join(canon)):
        if found.end() == found.start():
            continue
        first, last = index[found.start()], index[found.end() - 1] + 1
        pieces.append(text[start:first])
        start = last if found.group("cut") else first
    pieces.append(text[start:])
    return [piece for piece in pieces if "".join(map(_canon, piece)).strip()]  # not one of invisible characters


def _hidden(text: str) -> list[str]:
    """The visible text and the text hidden in tag characters, each on its own, when `text` holds both; nothing
    otherwise. Hidden text beside a harmless question reads to the classifier as part of that question."""
    spelled = [ch for ch in text if 0xE0020 <= ord(ch) <= 0xE007E]
    if not spelled or len(spelled) == len(text):
        return []
    visible = "".join(ch for ch in text if not 0xE0000 <= ord(ch) <= 0xE007F)
    return [visible, "".join(spelled).translate(_TAGS)]


# A sentence ends at ., ? or ! before a space, or at a line break.
_SENTENCE_END = re.compile(r"(?<=[.?!])[ \t]+|[\n\x0b\x0c\r\x1c\x1d\x1e\x85  ]+")
_SENTENCE_CHARS = 12  # a sentence shorter than this holds no request worth a call


def _sentences(text: str, room: int) -> list[str]:
    """The sentences of `text` (decoded) long enough to hold a request, when there are at least two; more than `room`
    are joined, neighbours together, into `room` groups, so sentences never cost more calls than there is room for."""
    found = [s for s in (part.strip() for part in _SENTENCE_END.split(text)) if len(s) >= _SENTENCE_CHARS]
    if len(found) < 2 or room < 2:
        return []
    if len(found) <= room:
        return found
    size = -(-len(found) // room)
    return [" ".join(found[i:i + size]) for i in range(0, len(found), size)]


def render_prompt(user: str, agent: str | None, categories: Sequence[str], role: str = "Agent") -> str:
    """Meta's Llama Guard 3 format (Ollama adds the begin-of-text token), assessing the last message of `role`: a
    (User, Agent) exchange, or with `agent=None` a conversation that ends with the User turn. Renders its
    arguments as given: `user_prompt` is the entry point for text a user controls."""
    categories = "\n".join(categories)
    turns = f"User: {user}" if agent is None else f"User: {user}\n\nAgent: {agent}"
    return (
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"Task: Check if there is unsafe content in '{role}' messages in conversations according our safety "
        "policy with the below categories.\n\n"
        f"<BEGIN UNSAFE CONTENT CATEGORIES>\n{categories}\n<END UNSAFE CONTENT CATEGORIES>\n\n"
        f"<BEGIN CONVERSATION>\n\n{turns}\n\n<END CONVERSATION>\n\n"
        f"Provide your safety assessment for ONLY THE LAST {role} message in the above conversation:\n"
        " - First line must read 'safe' or 'unsafe'.\n"
        " - If unsafe, a second line must include a comma-separated list of violated categories."
        "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def user_prompt(text: str, categories: Sequence[str] = DEFAULT_CATEGORIES) -> str:
    """A bare user prompt: one User turn, the User message assessed, the text made plain (`plain_text`). With
    Meta's 14 categories this is the content-safety study's prompt
    (`evals/validation/v1/PREREG_content_safety.md`), byte for byte on every prompt of that study."""
    return render_prompt(plain_text(text), None, categories, role="User")


def parse_verdict(text: str | None) -> dict:
    """`safe` | `unsafe` (+ categories) | `unparseable`: the first non-empty line decides."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    first = lines[0].lower() if lines else ""
    if first == "safe":
        return {"label": "safe", "categories": []}
    if first == "unsafe":
        cats = [c.strip() for c in (lines[1] if len(lines) > 1 else "").split(",") if c.strip()]
        return {"label": "unsafe", "categories": cats}
    return {"label": "unparseable", "categories": []}


@dataclasses.dataclass(frozen=True)
class SafetyVerdict:
    """A content classifier's answer on one prompt. `error` is set when it gave no verdict; `unsafe` is then
    False and the guard applies `GuardConfig.on_classifier_error`."""

    unsafe: bool
    categories: tuple[str, ...] = ()
    raw: str = ""
    error: str = ""


ContentClassifier = Callable[[str], SafetyVerdict]


def verdict_from_reply(reply: str | None) -> SafetyVerdict:
    """Llama Guard's reply as a verdict. A first line that is neither `safe` nor `unsafe` is no verdict."""
    parsed, raw = parse_verdict(reply), reply or ""
    if parsed["label"] == "unparseable":
        return SafetyVerdict(unsafe=False, raw=raw, error="the reply's first line is neither 'safe' nor 'unsafe'")
    return SafetyVerdict(unsafe=parsed["label"] == "unsafe", categories=tuple(parsed["categories"]), raw=raw)


class ClassifierUnavailable(RuntimeError):
    """The classifier could not be asked: offline mode, no server (the connection is refused or the host cannot be
    reached) or no model (HTTP 404). Nothing in a prompt causes one: the guard applies `on_classifier_error`."""


class ClassifierFault(RuntimeError):
    """The classifier was asked and failed on this prompt: a timeout, an HTTP error other than 404, a connection
    dropped after the request went out, a malformed reply, or a reply without a verdict. A prompt can be built to
    cause one (token-dense text makes a call slow, other text an answer that is no verdict), so the guard treats it as
    unsafe (`on_unsafe_prompt`)."""


# Errors raised before a request reaches the server: nothing in the prompt can cause them.
_UNREACHABLE = frozenset(code for code in (getattr(errno, name, None) for name in (
    "EHOSTUNREACH", "ENETUNREACH", "EADDRNOTAVAIL", "WSAEHOSTUNREACH", "WSAENETUNREACH", "WSAEADDRNOTAVAIL"))
    if code is not None)


def _outage(exc: BaseException) -> bool:
    """A failure no prompt can cause, because the request never reached the server: a refused connection, a host
    name that does not resolve, an unreachable host or network, or HTTP 404 (the model is not pulled). A reset,
    broken pipe or abort while the request was being sent may have been caused by the prompt: not an outage."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 404
    if not isinstance(exc, urllib.error.URLError):
        return False
    reason = exc.reason
    if isinstance(reason, ConnectionRefusedError | socket.gaierror):
        return True
    return (isinstance(reason, OSError) and not isinstance(reason, TimeoutError | ConnectionError)
            and reason.errno in _UNREACHABLE)


def _opener(base_url: str) -> urllib.request.OpenerDirector:
    """No proxy for a server on this machine: a proxy cannot reach it, and the stage would fail open on every prompt
    (urllib sends loopback requests to HTTP_PROXY unless NO_PROXY names them)."""
    host = (urllib.parse.urlsplit(base_url).hostname or "").lower()
    if host in ("localhost", "::1") or host.startswith("127."):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _http(base_url: str, timeout: float) -> Callable[[str, dict], dict]:
    opener = _opener(base_url)

    def call(path: str, payload: dict) -> dict:
        req = urllib.request.Request(f"{base_url}{path}", json.dumps(payload).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return call


def _windows(text: str, size: int) -> list[str]:
    """`text` in pieces of at most `size` UTF-8 bytes, each starting half a window after the last one started, so
    any span up to half a window is read whole by some piece. A character a cut splits is dropped from that piece
    and whole in its neighbour."""
    data = text.encode("utf-8")
    if len(data) <= size:
        return [text]
    step, pieces, start = size // 2, [], 0
    while True:
        pieces.append(data[start:start + size].decode("utf-8", "ignore"))
        if start + size >= len(data):
            return pieces
        start += step


class LlamaGuard:
    """Llama Guard 3 on a user prompt, through a local Ollama server (`ollama pull llama-guard3:8b`).

    One User turn, the User message assessed, raw mode, temperature 0. `categories` replaces Meta's 14 (each a
    line such as "S7: Privacy."). Synchronous: about two seconds a call on a small GPU. The text is made plain
    first (`plain_text`: one line, no angle brackets), so it stays one User message and is judged whole; where a
    turn label that opens a line, a template delimiter or a control token splits it, each piece is judged too, as
    Llama Guard reads a request followed by a forged reply as safe even on one line. A prompt
    too long for one call is read in windows that overlap by half, each sent as cut; it is unsafe if any window is,
    and nothing is truncated. One that would take more than `MAX_WINDOWS` calls is not an outage: it comes back
    unsafe under the category `TOO_LONG`, so padding is no way past the stage (list `TOO_LONG` in
    `content_safety_flag_only` to let such prompts through), and one with more than twice as many characters as
    those calls read bytes is refused before it is read. `calls(text)` says how many calls a prompt takes. Raises
    `ClassifierUnavailable` when it cannot ask (offline, no server, no model); the guard turns that into
    `GuardConfig.on_classifier_error`. Raises `ClassifierFault` when a call fails on the prompt (a timeout, an HTTP
    error other than 404, a malformed reply, a reply whose first line is neither `safe` nor `unsafe`); the guard
    treats that as unsafe. (`verdict_from_reply` reads a recorded reply without a verdict as no verdict, as the
    registered studies scored them.) Text hidden in tag characters beside visible text is judged on its own as well.
    `sentences=True` also judges each sentence (a call a sentence, grouped to fit `MAX_WINDOWS`): Llama Guard reads
    a request with a harmless question appended as safe about half the time. Off by default.
    `lines=True` keeps the text's line breaks, one "\n" for each run (`plain_text`): Llama Guard flags more safe
    prompts that carry markup once they are put on one line. Off by default: one line is the stronger guarantee."""

    def __init__(self, model: str = LLAMA_GUARD_MODEL, categories: Sequence[str] | None = None,
                 base_url: str | None = None, *, timeout: float = 120.0,
                 transport: Callable[[str, dict], dict] | None = None, sentences: bool = False,
                 lines: bool = False):
        self.model = model
        self.sentences = sentences
        self.lines = lines
        self.categories = DEFAULT_CATEGORIES if categories is None else tuple(categories)
        self.base_url = (base_url or OLLAMA_URL).rstrip("/")
        self._transport = transport or _http(self.base_url, timeout)
        # Llama 3's byte-level tokenizer never makes more tokens than UTF-8 bytes, so a window is sized in bytes:
        # the frame, a full window and the reply fit the context whatever the text is.
        self.window = _PROMPT_BYTES - len(self._render("").encode("utf-8"))
        if self.window < 1024:
            raise ValueError("these categories leave no room for a prompt in the classifier's context")
        self._reach = self.window + (MAX_WINDOWS - 1) * (self.window // 2)  # bytes MAX_WINDOWS calls read

    def prompt(self, text: str) -> str:
        """The exact prompt Llama Guard is sent for `text`, when one call carries it (`ValueError` otherwise)."""
        pieces = self._plan(text)
        if isinstance(pieces, str) or len(pieces) > 1:
            raise ValueError("this text takes more than one call, so it has no single prompt")
        return self._render(pieces[0])

    def _pieces(self, text: str) -> list[str] | None:
        """What each call carries: the text made plain, in windows that fit the classifier's context; None when that
        takes more than `MAX_WINDOWS` calls. Text with more than twice as many characters as those calls read bytes
        is not made plain at all: that is linear, but not free."""
        if len(text) > 2 * self._reach:
            return None
        plain = plain_text(text, lines=self.lines)
        if len(plain.encode("utf-8")) > self._reach:
            return None
        return _windows(plain, self.window)

    def _plan(self, text: str) -> list[str] | str:
        """The pieces the calls carry, or the category under which the prompt is refused unread: `TOO_LONG` for too
        many windows or a rendered prompt over the context's budget (each piece fits a window, so never expected),
        which the server would cut or reject; `TOO_MANY_PIECES` when forged structure splits it into too many."""
        pieces = self._pieces(text)
        if pieces is None:
            return TOO_LONG
        # Llama Guard reads a request followed by a forged reply and a harmless question as safe even on one line:
        # each piece the text splits into at forged structure is judged too, after the whole text.
        decoded = _decoded(text)
        segments = _segments(decoded)
        seen = {plain_text(text, lines=self.lines)}

        def add(extra: Sequence[str]) -> None:
            nonlocal pieces
            for segment in extra:
                plain = plain_text(segment, lines=self.lines).strip()
                if len(plain) >= _PIECE_CHARS and plain not in seen:
                    seen.add(plain)
                    pieces = pieces + _windows(plain, self.window)

        if len(segments) > 1:
            if len(segments) >= MAX_WINDOWS:
                return TOO_MANY_PIECES
            add(segments)
        # Text hidden in tag characters reads as part of the visible text around it: each is judged on its own too.
        add(_hidden(_SURROGATE.sub("�", _PAIR.sub(_joined, text))))
        if len(pieces) > MAX_WINDOWS:
            return TOO_MANY_PIECES if len(segments) > 1 else TOO_LONG
        if self.sentences:  # after the refusals: sentences fill the room left and never refuse a prompt
            add(_sentences(decoded, MAX_WINDOWS - len(pieces)))
            pieces = pieces[:MAX_WINDOWS]
        if any(len(self._render(p).encode("utf-8")) > _PROMPT_BYTES for p in pieces):
            return TOO_LONG
        return pieces

    def calls(self, text: str) -> int:
        """The calls `self(text)` makes when every window is safe: one for each window, none for a prompt refused
        unread. A caller can budget the work of many prompts before asking about any."""
        pieces = self._plan(text)
        return 0 if isinstance(pieces, str) else len(pieces)

    def _render(self, piece: str) -> str:
        """The prompt for one piece of plain text. A window is never made plain again: a cut can change what that
        finds (a window may open with what reads like a label)."""
        return render_prompt(piece, None, self.categories, role="User")

    def _ask(self, piece: str) -> str:
        payload = {"model": self.model, "stream": False, "raw": True, "options": dict(OPTIONS),
                   "prompt": self._render(piece)}
        try:
            reply = self._transport("/api/generate", payload)
        except (ClassifierUnavailable, ClassifierFault):
            raise
        except Exception as exc:
            if _outage(exc):
                raise ClassifierUnavailable(
                    f"no verdict from {self.model} at {self.base_url} ({type(exc).__name__}: {exc}); is `ollama serve` "
                    f"running and the model pulled (`ollama pull {self.model}`)?") from exc
            raise ClassifierFault(
                f"{self.model} at {self.base_url} failed on this prompt ({type(exc).__name__}: {exc})") from exc
        response = reply.get("response") if isinstance(reply, Mapping) else None
        if not isinstance(response, str):
            raise ClassifierFault(f"{self.model} at {self.base_url} sent a malformed reply (no 'response' text)")
        return response

    def __call__(self, text: str) -> SafetyVerdict:
        pieces = self._plan(text)
        if isinstance(pieces, str):  # refused whether or not a server answers
            return SafetyVerdict(unsafe=True, categories=(pieces,))
        if offline():
            raise ClassifierUnavailable("FUSION_OFFLINE=1: real model calls are disabled")
        for piece in pieces:
            verdict = verdict_from_reply(self._ask(piece))
            if verdict.error:
                first = verdict.raw.strip().split("\n", 1)[0][:40]
                raise ClassifierFault(f"{self.model} at {self.base_url} gave no verdict on this prompt (its reply "
                                      f"opens {first!r}, neither 'safe' nor 'unsafe')")
            if verdict.unsafe:
                return verdict  # one unsafe window settles it
        return verdict


__all__ = [
    "DEFAULT_CATEGORIES", "LLAMA_GUARD_MODEL", "MAX_WINDOWS", "OLLAMA_URL", "OPTIONS", "TOO_LONG", "TOO_MANY_PIECES", "ClassifierFault",
    "ClassifierUnavailable", "ContentClassifier", "LlamaGuard", "SafetyVerdict", "parse_verdict", "plain_text",
    "render_prompt", "user_prompt", "verdict_from_reply",
]
