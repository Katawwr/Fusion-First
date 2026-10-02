"""Live OpenAI adapter over the async SDK (imported lazily; metered, opt-in only): the cross-family judge."""

from __future__ import annotations

from fusion_first.model.client import ModelRequest, ModelResponse, ModelRole
from fusion_first.model.providers._common import is_bad_request, resolve_model, strictify_schema
from fusion_first.model.registry import ModelRegistry

_ROLE_MAP = {
    ModelRole.JUDGE: "judge_cross_family",
    ModelRole.CALIBRATION: "judge_cross_family",
    ModelRole.PREFILTER: "judge_cross_family",
}


class OpenAIModelClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client=None,
        registry: ModelRegistry | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        self._api_key = api_key
        self._client = client
        self._registry = registry or ModelRegistry()
        self._timeout = timeout
        self._max_retries = max_retries

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._api_key, timeout=self._timeout, max_retries=self._max_retries
            )
        return self._client

    async def complete(self, request: ModelRequest) -> ModelResponse:
        client = self._ensure_client()
        model = resolve_model(self._registry, request, _ROLE_MAP)

        messages = list(request.messages)
        if request.system:
            messages = [{"role": "system", "content": request.system}, *messages]
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        used_schema = request.response_schema is not None
        if used_schema:
            strict = strictify_schema(request.response_schema)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "verdict", "schema": strict, "strict": True},
            }

        try:
            resp = await client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if used_schema and is_bad_request(exc):
                kwargs.pop("response_format", None)
                resp = await client.chat.completions.create(**kwargs)
            else:
                raise
        return _to_response(resp, model)


def _to_response(resp, model: str) -> ModelResponse:
    choice = resp.choices[0]
    finish = getattr(choice, "finish_reason", None)
    text = getattr(choice.message, "content", None) or ""
    if finish in {"content_filter", "refusal"}:
        text = ""  # fail closed
    usage = getattr(resp, "usage", None)
    return ModelResponse(
        text=text,
        model=getattr(resp, "model", model),
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        stop_reason=finish,
    )
