"""A target backed by any OpenAI-compatible chat-completions server — test YOUR model where it runs:
vLLM, LM Studio, llama.cpp's server, text-generation-inference, Ollama's /v1, and so on.

Dependency-free (stdlib urllib, run off the event loop) and modal-free. Whether an endpoint may be used
without the metered opt-in is decided by the resolver (`fusion.backends.resolve`): local and private
network servers are free to use; a public endpoint may be a metered API and needs FUSION_ALLOW_API_SPEND=1.
An optional bearer key is read from FUSION_TARGET_API_KEY, or from a provider preset's own variable
(never logged, never stored in a run).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request

from fusion.errors import FusionProviderError
from fusion.model.client import ModelRequest, ModelResponse
from fusion.offline import offline

API_KEY_ENV = "FUSION_TARGET_API_KEY"


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect. The stdlib would re-send the request, bearer key included, to whatever
    host the redirect names: a host the zero-spend gate never checked. A chat-completions endpoint has
    no reason to redirect, so a redirect is an error that names where it pointed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # the default error handler then raises HTTPError(code)


_OPENER = urllib.request.build_opener(_NoRedirects)


class OpenAICompatUnavailable(FusionProviderError):
    """The server could not answer (not running, wrong URL or model, or a network error)."""


class OpenAICompatModelClient:
    def __init__(self, base_url: str, model: str, *, timeout: float = 600.0, api_key_env: str = API_KEY_ENV):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._api_key_env = api_key_env  # a provider preset reads its own variable (OPENAI_API_KEY, HF_TOKEN...)

    def _payload(self, request: ModelRequest) -> dict:
        messages: list[dict] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        payload: dict = {"model": self._model, "messages": messages, "max_tokens": request.max_tokens,
                         "temperature": request.temperature, "stream": False}
        if request.seed is not None:
            payload["seed"] = request.seed
        return payload

    def _post(self, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self._api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(f"{self._base_url}/chat/completions",
                                     data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with _OPENER.open(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                raise OpenAICompatUnavailable(
                    f"{self._base_url} answered with a redirect (HTTP {e.code}) to "
                    f"{e.headers.get('Location', 'an unnamed location')}; refusing to follow it — point the "
                    "target at the final server URL") from e
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except OSError:
                pass
            raise OpenAICompatUnavailable(f"{self._base_url} returned HTTP {e.code} for {self._model}: {body}") from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise OpenAICompatUnavailable(
                f"could not reach the OpenAI-compatible server at {self._base_url} ({e}); is it running, and "
                f"is '{self._model}' the model it serves?"
            ) from e

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if offline():
            raise OpenAICompatUnavailable("FUSION_OFFLINE=1: real model calls are disabled")
        started = time.monotonic()
        data = await asyncio.to_thread(self._post, self._payload(request))
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise OpenAICompatUnavailable(f"{self._base_url} sent an unexpected reply: {str(data)[:200]}") from e
        usage = data.get("usage") or {}
        return ModelResponse(
            text=text, model=self._model, served_model=data.get("model"),
            input_tokens=int(usage.get("prompt_tokens") or 0), output_tokens=int(usage.get("completion_tokens") or 0),
            stop_reason=choice.get("finish_reason"), truncated=choice.get("finish_reason") == "length",
            latency_s=round(time.monotonic() - started, 3),
        )
