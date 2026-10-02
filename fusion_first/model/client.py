"""The ModelClient interface, request/response objects, and the request hash cassettes are keyed on."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ModelRole(str, Enum):
    TARGET = "target"  # the customer's model-under-test
    JUDGE = "judge"  # the calibrated evaluator
    PREFILTER = "prefilter"  # cheap first pass
    CALIBRATION = "calibration"  # strongest model, for proof/benchmarks


class ModelRequest(BaseModel):
    role: ModelRole
    system: str = ""
    messages: list[dict] = Field(default_factory=list)  # [{"role": ..., "content": ...}]
    max_tokens: int = 1024
    temperature: float = 0.0
    # When set, the provider is asked to return JSON matching this schema (structured output).
    response_schema: dict | None = None
    # Optional explicit model id, overriding the role default from the registry.
    model_id: str | None = None
    # Ask for the top-N token log-probabilities (probability judges; Ollama). None = not requested.
    logprobs: int | None = None
    # Sampling seed for providers that honour one (Ollama). None = provider default.
    seed: int | None = None

    def cache_key(self) -> str:
        """Stable cassette key: includes everything that affects output."""
        payload = {
            "role": self.role.value,
            "system": self.system,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "response_schema": self.response_schema,
            "model_id": self.model_id,
        }
        # Newer fields enter the key only when set, so existing cassette keys are unchanged.
        if self.logprobs is not None:
            payload["logprobs"] = self.logprobs
        if self.seed is not None:
            payload["seed"] = self.seed
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ModelResponse(BaseModel):
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None
    # Optional extras, absent in older cassettes.
    served_model: str | None = None  # the model that actually answered, when the provider says
    truncated: bool = False  # output hit the length limit (a truncated answer is not trustworthy)
    latency_s: float | None = None
    # Per output token: {"token": str, "logprob": float, "top": [{"token","logprob"}...]}.
    top_logprobs: list[dict] | None = None


@runtime_checkable
class ModelClient(Protocol):
    """Every model access point in the system implements exactly this."""

    async def complete(self, request: ModelRequest) -> ModelResponse: ...
