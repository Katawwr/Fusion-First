"""Request bodies for the API. Responses are `fusion_first.schemas` models dumped to JSON directly."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from fusion_first.judge.rubric import REGISTRY


def _check_known(checks: list[str] | None) -> list[str] | None:
    if checks is None:
        return None
    unknown = [c for c in checks if c not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown checks: {unknown}; valid: {sorted(REGISTRY)}")
    return checks


class ScanRequest(BaseModel):
    system_prompt: str = Field(min_length=1)
    checks: list[str] | None = None
    tier: str = "quick"
    mode: str | None = None  # "demo" | "live" | None (defaults to demo)
    backend: str | None = None  # "api" | "cli" | "ollama" | "spec" | None (live only)
    target_model: str | None = None  # e.g. "llama3.2:1b" with backend="ollama"
    target_spec: str | None = Field(default=None, max_length=500)  # backend="spec": openai:gpt-4o-mini, hf:...
    grader_spec: str | None = Field(default=None, max_length=500)  # backend="spec": default claude-cli
    hardened_prompt: str | None = Field(default=None, min_length=1)  # the edited prompt to measure (live only)

    @field_validator("checks")
    @classmethod
    def _checks(cls, v):
        return _check_known(v)

    @field_validator("tier")
    @classmethod
    def _tier(cls, v):
        if v not in ("quick", "full"):
            raise ValueError("tier must be 'quick' or 'full'")
        return v

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        if v is not None and v not in ("demo", "live"):
            raise ValueError("mode must be 'demo' or 'live'")
        return v

    @field_validator("backend")
    @classmethod
    def _backend(cls, v):
        if v is not None and v not in ("api", "cli", "ollama", "spec"):
            raise ValueError("backend must be one of api, cli, ollama, spec")
        return v


class HardenRequest(BaseModel):
    system_prompt: str = Field(min_length=1)
    checks: list[str] | None = None

    @field_validator("checks")
    @classmethod
    def _checks(cls, v):
        return _check_known(v)


class GuardrailRequest(BaseModel):
    checks: list[str] | None = None

    @field_validator("checks")
    @classmethod
    def _checks(cls, v):
        return _check_known(v)


class QualityRequest(BaseModel):
    """Quality (correctness / instruction-following) grading; live-only."""

    system_prompt: str = Field(min_length=1)
    checks: list[str] | None = None
    target_model: str | None = None
    backend: str | None = None  # "cli" | "ollama" | "api" | None (auto)

    @field_validator("checks")
    @classmethod
    def _checks(cls, v):
        return _check_known(v)

    @field_validator("backend")
    @classmethod
    def _backend(cls, v):
        if v is not None and v not in ("auto", "cli", "ollama", "api"):
            raise ValueError("backend must be one of auto, cli, ollama, api")
        return v
