"""Live Anthropic adapter over the async SDK (imported lazily; metered, opt-in only).

The 2026 tiers reject `temperature`, so it is omitted and thinking disabled for them. A refusal
yields empty text, so the judge fails closed.
"""

from __future__ import annotations

from fusion_first.model.client import ModelRequest, ModelResponse, ModelRole
from fusion_first.model.providers._common import is_bad_request, resolve_model, strictify_schema
from fusion_first.model.registry import ModelRegistry

# Models that reject sampling params (temperature/top_p/top_k).
_NO_SAMPLING = {
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-fable-5",
    "claude-mythos-5",
}

_ROLE_MAP = {
    ModelRole.JUDGE: "judge_primary",
    ModelRole.CALIBRATION: "judge_calibration",
    ModelRole.PREFILTER: "judge_prefilter",
    # TARGET absent: a target model must be named explicitly.
}


class AnthropicModelClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client=None,
        registry: ModelRegistry | None = None,
        judge_model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        self._api_key = api_key
        self._client = client
        self._registry = registry or ModelRegistry()
        # Overrides the role-default judge tier without changing the request's cache key. Allowlisted.
        self._judge_model = judge_model
        self._timeout = timeout
        self._max_retries = max_retries

    def _resolve(self, request: ModelRequest) -> str:
        judge_role = request.role in (ModelRole.JUDGE, ModelRole.CALIBRATION)
        if self._judge_model and judge_role and request.model_id is None:
            self._registry.require_allowed(self._judge_model)
            return self._judge_model
        return resolve_model(self._registry, request, _ROLE_MAP)

    def _ensure_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self._api_key, timeout=self._timeout, max_retries=self._max_retries
            )
        return self._client

    async def complete(self, request: ModelRequest) -> ModelResponse:
        client = self._ensure_client()
        model = self._resolve(request)

        kwargs: dict = {
            "model": model,
            "max_tokens": request.max_tokens,
            "messages": request.messages,
        }
        if request.system:
            kwargs["system"] = request.system
        if model in _NO_SAMPLING:
            kwargs["thinking"] = {"type": "disabled"}
        else:
            kwargs["temperature"] = request.temperature

        used_schema = request.response_schema is not None
        if used_schema:
            strict = strictify_schema(request.response_schema)
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": strict}}

        try:
            msg = await client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if used_schema and is_bad_request(exc):
                # Some models reject structured output: fall back to prompt-driven JSON.
                kwargs.pop("output_config", None)
                msg = await client.messages.create(**kwargs)
            else:
                raise
        return _to_response(msg, model)


def _to_response(msg, model: str) -> ModelResponse:
    if getattr(msg, "stop_reason", None) == "refusal":
        text = ""  # fail closed: an empty verdict makes the judge raise JudgeParseError
    else:
        text = "".join(
            getattr(b, "text", "") for b in getattr(msg, "content", []) if getattr(b, "type", None) == "text"
        )
    usage = getattr(msg, "usage", None)
    return ModelResponse(
        text=text,
        model=getattr(msg, "model", model),
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        stop_reason=getattr(msg, "stop_reason", None),
    )
