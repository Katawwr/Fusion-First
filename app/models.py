"""Request bodies for the API. Responses are `fusion.schemas` models dumped to JSON directly."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from fusion.judge.rubric import REGISTRY


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
