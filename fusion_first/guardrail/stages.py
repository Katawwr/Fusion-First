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
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence

from fusion_first.offline import offline
from fusion_first.security.normalize import fold

LLAMA_GUARD_MODEL = "llama-guard3:8b"
# IPv4 loopback, as the Ollama provider: on Windows `localhost` tries ::1 first.
OLLAMA_URL = "http://127.0.0.1:11434"
# Deterministic, and room for two lines only: the verdict and the categories.
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 24}
MAX_WINDOWS = 32  # calls one prompt may take
TOO_LONG = "too long to classify"  # the category LlamaGuard gives a prompt that would take more calls: refused

# Meta's 14 hazard categories, as Llama Guard 3's own template lists them.
DEFAULT_CATEGORIES = (
    "S1: Violent Crimes.", "S2: Non-Violent Crimes.", "S3: Sex Crimes.", "S4: Child Exploitation.",
    "S5: Defamation.", "S6: Specialized Advice.", "S7: Privacy.", "S8: Intellectual Property.",
    "S9: Indiscriminate Weapons.", "S10: Hate.", "S11: Self-Harm.", "S12: Sexual Content.",
    "S13: Elections.", "S14: Code Interpreter Abuse.",
)

# Raw mode tokenizes control-token strings wherever they appear: none may come from the user.
_CONTROL_TOKEN = re.compile(r"<(?=\|)")
# The prompt's own delimiter lines, matched on a line's folded form (look-alike letters, zero-width and full-width
# characters fold to ASCII), however they are spaced.
_DELIMITER = re.compile(r"<\s*(?:BEGIN|END)\s+(?:CONVERSATION|UNSAFE\s+CONTENT\s+CATEGORIES)\s*>", re.IGNORECASE)
_ANGLES = str.maketrans({"<": "\u2039", "\uff1c": "\u2039", "\ufe64": "\u2039",
                         ">": "\u203a", "\uff1e": "\u203a", "\ufe65": "\u203a"})
# A line that opens like a turn of the conversation, after any markdown or quote marks, matched on its folded form.
# Llama Guard is asked about the LAST User message, so a forged turn could hide a request in an earlier one.
_TURN_LABEL = re.compile(
    r"^[\s>*_#`~|-]*(?:user|agent|assistant|human|system|ai|bot|chatbot|model)[\s*_`~]*:", re.IGNORECASE)
_LABEL_SCAN = 80  # characters of a line read for a label
# A lone surrogate cannot be encoded, so it would make the prompt unsendable.
_SURROGATE = re.compile("[\ud800-\udfff]")


def _strip_labels(line: str) -> str:
    """The line without the conversation-turn labels it opens with (one or several), the line break kept."""
    while _TURN_LABEL.match(fold(line[:_LABEL_SCAN])):
        for end in range(1, min(len(line), _LABEL_SCAN) + 1):
            if _TURN_LABEL.match(fold(line[:end])):
                line = line[end:].lstrip(" \t\u00a0")
                break
        else:
            break
    return line


def plain_text(text: str) -> str:
    """User text that cannot act as part of the prompt, whatever it holds:

    - a lone surrogate becomes U+FFFD, so the text can always be sent;
    - a conversation-turn label at a line start ("User:", "Agent:", look-alikes and markdown included) is dropped,
      so the text stays one User message and is judged whole;
    - a line holding a BEGIN/END delimiter of the prompt gets its angle brackets as \u2039 \u203a;
    - Llama 3's control tokens (`<|...|>`) get a space after their `<`.

    Text without any of these is returned unchanged, so recorded renderings keep their hashes. Idempotent."""
    text = _SURROGATE.sub("\ufffd", text)
    lines = []
    for line in text.splitlines(keepends=True):
        line = _strip_labels(line)
        if _DELIMITER.search(fold(line)):
            line = line.translate(_ANGLES)
        lines.append(line)
    return _CONTROL_TOKEN.sub("< ", "".join(lines))


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
    """The classifier could not be asked: offline mode, no server, no model or no usable reply."""


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
    first (`plain_text`: turn labels dropped, so a message is judged whole). A prompt too long for one call is read
    in windows that overlap by half; it is unsafe if any window is, and nothing is truncated. One that would take
    more than `MAX_WINDOWS` calls is not an outage: it comes back unsafe under the category `TOO_LONG`, so padding
    is no way past the stage (list `TOO_LONG` in `content_safety_flag_only` to let such prompts through). Raises
    `ClassifierUnavailable` when it cannot ask; the guard turns that into `GuardConfig.on_classifier_error`."""

    def __init__(self, model: str = LLAMA_GUARD_MODEL, categories: Sequence[str] | None = None,
                 base_url: str | None = None, *, timeout: float = 120.0,
                 transport: Callable[[str, dict], dict] | None = None):
        self.model = model
        self.categories = DEFAULT_CATEGORIES if categories is None else tuple(categories)
        self.base_url = (base_url or OLLAMA_URL).rstrip("/")
        self._transport = transport or _http(self.base_url, timeout)
        # Llama 3's byte-level tokenizer never makes more tokens than UTF-8 bytes, so a window is sized in bytes:
        # the frame, a full window and the reply fit the context whatever the text is.
        frame = len(user_prompt("", self.categories).encode("utf-8"))
        self.window = OPTIONS["num_ctx"] - OPTIONS["num_predict"] - frame - 16
        if self.window < 1024:
            raise ValueError("these categories leave no room for a prompt in the classifier's context")

    def prompt(self, text: str) -> str:
        """The exact prompt Llama Guard is sent for `text`, when one call carries it (`ValueError` otherwise)."""
        piece, *more = self._pieces(text)
        if more:
            raise ValueError("this text takes more than one call, so it has no single prompt")
        return user_prompt(piece, self.categories)

    def _pieces(self, text: str) -> list[str]:
        """What each call carries: the text made plain, in windows that fit the classifier's context."""
        return _windows(plain_text(text), self.window)

    def _ask(self, piece: str) -> str:
        payload = {"model": self.model, "stream": False, "raw": True, "options": dict(OPTIONS),
                   "prompt": user_prompt(piece, self.categories)}
        try:
            return self._transport("/api/generate", payload)["response"]
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, TypeError, ValueError) as exc:
            raise ClassifierUnavailable(
                f"no verdict from {self.model} at {self.base_url} ({type(exc).__name__}: {exc}); is `ollama serve` "
                f"running and the model pulled (`ollama pull {self.model}`)?") from exc

    def __call__(self, text: str) -> SafetyVerdict:
        pieces = self._pieces(text)
        if len(pieces) > MAX_WINDOWS:
            return SafetyVerdict(unsafe=True, categories=(TOO_LONG,))  # refused whether or not a server answers
        if offline():
            raise ClassifierUnavailable("FUSION_OFFLINE=1: real model calls are disabled")
        undecided = verdict = None
        for piece in pieces:
            verdict = verdict_from_reply(self._ask(piece))
            if verdict.unsafe:
                return verdict  # one unsafe window settles it
            undecided = undecided or (verdict if verdict.error else None)
        return undecided or verdict


__all__ = [
    "DEFAULT_CATEGORIES", "LLAMA_GUARD_MODEL", "MAX_WINDOWS", "OLLAMA_URL", "OPTIONS", "TOO_LONG",
    "ClassifierUnavailable", "ContentClassifier", "LlamaGuard", "SafetyVerdict", "parse_verdict", "plain_text",
    "render_prompt", "user_prompt", "verdict_from_reply",
]
