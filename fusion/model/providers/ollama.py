"""Local open-weight target adapter via Ollama — the product's sweet spot.

Frontier models (Claude, GPT-4-class) are heavily safety-tuned and resist most injection / exfil /
excessive-agency attacks. Open-weight models (Llama, Mistral, Qwen, Phi, Gemma, …) are far less
robust, so those attacks actually LAND — which is exactly where Fusion finds and fixes real
vulnerabilities. Ollama runs them locally for free with no API key, matching Fusion's no-cost posture.

The ideal configuration this enables: a WEAK open-weight *target* judged by a strong, calibrated
Claude *judge* — genuine CROSS-FAMILY independence (the honest judging tier), better than
Claude-judging-Claude.

Dependency-free (stdlib urllib run off the event loop) and modal-free, so importing `fusion` never
requires Ollama to be installed or running.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from fusion.model.client import ModelRequest, ModelResponse

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaUnavailable(RuntimeError):
    """Ollama could not serve the request (server not running, model not pulled, or a network error)."""


class OllamaModelClient:
    """A ModelClient backed by a local Ollama server (open-weight models, free, no API key)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ):
        self._base_url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
        self._default_model = model
        self._timeout = timeout

    def _resolve_model(self, request: ModelRequest) -> str:
        model = request.model_id or self._default_model
        if not model:
            raise OllamaUnavailable("no Ollama model specified (set model_id or the client default)")
        # Accept a friendly "ollama:<name>" or "ollama/<name>" prefix and strip it for the API.
        for sep in ("ollama:", "ollama/"):
            if model.startswith(sep):
                model = model[len(sep):]
        return model

    def _build_payload(self, request: ModelRequest, model: str) -> dict:
        messages: list[dict] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        if request.response_schema is not None:
            # Ollama honours a JSON schema (newer) or the "json" keyword (older) as the format hint.
            payload["format"] = request.response_schema
        return payload

    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}{path}", data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # OSError covers socket.timeout / ConnectionReset / ConnectionRefused — the dominant
            # failure modes for slow local generation — so they surface as OllamaUnavailable, not raw.
            raise OllamaUnavailable(
                f"could not reach Ollama at {self._base_url} ({e}); is `ollama serve` running "
                "and the model pulled (`ollama pull <model>`)?"
            ) from e

    async def complete(self, request: ModelRequest) -> ModelResponse:
        model = self._resolve_model(request)
        payload = self._build_payload(request, model)
        data = await asyncio.to_thread(self._post, "/api/chat", payload)
        message = data.get("message") or {}
        text = message.get("content", "")
        if not isinstance(text, str):
            text = str(text)
        return ModelResponse(
            text=text,
            model=model,
            input_tokens=int(data.get("prompt_eval_count", 0) or 0),
            output_tokens=int(data.get("eval_count", 0) or 0),
            stop_reason=data.get("done_reason", "stop"),
        )


def ollama_available(base_url: str | None = None) -> bool:
    """True if a local Ollama server answers (used to auto-select the backend)."""
    url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False
