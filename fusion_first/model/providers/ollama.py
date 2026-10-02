"""Local open-weight models via Ollama (stdlib only).

`num_ctx` is set explicitly and an over-long request is refused up front: Ollama would otherwise
silently drop the head of the system prompt. `done_reason == "length"` marks a truncated answer;
`logprobs` (Ollama >= 0.12.11) power the probability judge.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request

from fusion_first.errors import FusionProviderError, PromptTooLong
from fusion_first.model.client import ModelRequest, ModelResponse
from fusion_first.offline import offline

# IPv4 loopback, not `localhost`: on Windows `localhost` tries ::1 first, a ~2 s fallback per request.
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_NUM_CTX = 8192
# Conservative characters-per-token for the up-front context check (English ≈ 4, code/JSON ≈ 3).
_CHARS_PER_TOKEN = 3.0


class OllamaUnavailable(FusionProviderError):
    """Ollama could not serve the request (server not running, model not pulled, or a network error)."""


class OllamaContextTooLong(OllamaUnavailable, PromptTooLong):
    """The request would overflow the context window: refused instead of silently truncated."""


class OllamaModelClient:
    """A ModelClient backed by a local Ollama server (open-weight models, free, no API key)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 300.0,
        num_ctx: int = DEFAULT_NUM_CTX,
        keep_alive: str | None = "30m",
    ):
        self._base_url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
        self._default_model = model
        self._timeout = timeout
        self._num_ctx = num_ctx
        self._keep_alive = keep_alive

    def _resolve_model(self, request: ModelRequest) -> str:
        model = request.model_id or self._default_model
        if not model:
            raise OllamaUnavailable("no Ollama model specified (set model_id or the client default)")
        # Strip an "ollama:" or "ollama/" prefix.
        for sep in ("ollama:", "ollama/"):
            if model.startswith(sep):
                model = model[len(sep):]
        if model.startswith(("claude-", "gpt-", "o1", "o3")):
            raise OllamaUnavailable(
                f"'{model}' is a hosted model id, not an Ollama model — pick a local model such as "
                "llama3.2:1b or qwen2.5:3b (`ollama list`)"
            )
        return model

    def _estimate_tokens(self, request: ModelRequest) -> int:
        chars = len(request.system) + sum(len(str(m.get("content", ""))) for m in request.messages)
        return int(chars / _CHARS_PER_TOKEN) + 16 * (len(request.messages) + 1)

    def _check_context(self, request: ModelRequest) -> None:
        needed = self._estimate_tokens(request) + request.max_tokens
        if needed > self._num_ctx:
            raise OllamaContextTooLong(
                f"request needs ~{needed} tokens but num_ctx is {self._num_ctx}; refusing rather than "
                "letting Ollama silently drop the start of the prompt"
            )

    def _build_payload(self, request: ModelRequest, model: str) -> dict:
        messages: list[dict] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        options: dict = {
            "temperature": request.temperature,
            "num_predict": request.max_tokens,
            "num_ctx": self._num_ctx,
        }
        if request.seed is not None:
            options["seed"] = request.seed
        payload: dict = {"model": model, "messages": messages, "stream": False, "options": options}
        if self._keep_alive:
            payload["keep_alive"] = self._keep_alive
        if request.response_schema is not None:
            payload["format"] = request.response_schema
        if request.logprobs:
            payload["logprobs"] = True
            payload["top_logprobs"] = int(request.logprobs)
        return payload

    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}{path}", data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except OSError:
                pass
            raise OllamaUnavailable(f"Ollama returned HTTP {e.code} for {payload.get('model')}: {body}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise OllamaUnavailable(
                f"could not reach Ollama at {self._base_url} ({e}); is `ollama serve` running "
                "and the model pulled (`ollama pull <model>`)?"
            ) from e

    @staticmethod
    def _parse_logprobs(raw: object) -> list[dict] | None:
        if not isinstance(raw, list):
            return None
        out: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            top = [
                {"token": str(t.get("token", "")), "logprob": float(t.get("logprob", float("-inf")))}
                for t in (item.get("top_logprobs") or [])
                if isinstance(t, dict)
            ]
            out.append({
                "token": str(item.get("token", "")),
                "logprob": float(item.get("logprob", float("-inf"))),
                "top": top,
            })
        return out

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if offline():
            raise OllamaUnavailable("FUSION_OFFLINE=1: real model calls are disabled")
        model = self._resolve_model(request)
        self._check_context(request)
        payload = self._build_payload(request, model)
        started = time.monotonic()
        data = await asyncio.to_thread(self._post, "/api/chat", payload)
        message = data.get("message") or {}
        text = message.get("content", "")
        if not isinstance(text, str):
            text = str(text)
        done_reason = data.get("done_reason", "stop")
        return ModelResponse(
            text=text,
            model=model,
            input_tokens=int(data.get("prompt_eval_count", 0) or 0),
            output_tokens=int(data.get("eval_count", 0) or 0),
            stop_reason=done_reason,
            served_model=str(data.get("model") or model),
            truncated=done_reason == "length",
            latency_s=round(time.monotonic() - started, 3),
            top_logprobs=self._parse_logprobs(data.get("logprobs")) if request.logprobs else None,
        )


def ollama_available(base_url: str | None = None) -> bool:
    """A local Ollama server answers and FUSION_OFFLINE is not set."""
    if offline():
        return False
    url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def ollama_models(base_url: str | None = None) -> list[dict]:
    """Installed local models: [{name, digest, size, family, parameter_size}] ([] if unreachable)."""
    if offline():
        return []
    url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    out = []
    for m in data.get("models", []) or []:
        details = m.get("details") or {}
        out.append({
            "name": m.get("name", ""),
            "digest": m.get("digest", ""),
            "size": m.get("size", 0),
            "family": details.get("family", ""),
            "parameter_size": details.get("parameter_size", ""),
        })
    return out


def model_digest(name: str, base_url: str | None = None) -> str | None:
    """The installed digest of a local model (pins evidence to exact weights)."""
    for m in ollama_models(base_url):
        if m["name"] == name or m["name"] == f"{name}:latest":
            return m["digest"]
    return None
