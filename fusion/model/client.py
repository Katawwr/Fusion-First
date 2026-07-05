"""The ModelClient interface plus request/response value objects and a stable request hash.

The hash is what cassettes are keyed on, so it must be deterministic and must exclude nothing
that changes the model output. Provider adapters and the replay client all speak this interface.
"""

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

    def cache_key(self) -> str:
        """Stable content hash used to key cassettes. Includes everything that affects output."""
        payload = {
            "role": self.role.value,
            "system": self.system,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "response_schema": self.response_schema,
            "model_id": self.model_id,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ModelResponse(BaseModel):
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None


@runtime_checkable
class ModelClient(Protocol):
    """Every model access point in the system implements exactly this."""

    async def complete(self, request: ModelRequest) -> ModelResponse: ...
