"""Runtime settings, read from the environment.

Keys live server-side only and are never returned to the client. When no provider key is present,
the app runs in demo mode — every scan is a clearly-badged demonstration.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from fusion_first import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # Provider keys (server-side only). Presence of ANTHROPIC_API_KEY enables real scans.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Scan execution knobs.
    target_model: str = "claude-haiku-4-5"  # cheap default for running the user's prompt live
    scan_max_calls: int = 400  # per-scan model-call ceiling (BudgetedModelClient)
    prompt_max_chars: int = 32_000
    sse_heartbeat_s: float = 15.0  # keepalive comment interval for long live scans

    # Reported by /api/credits; not enforced (no accounts).
    free_scans_per_day: int = 3

    # Fail-closed webhook signature (the webhook has no effect; the signature gate is real).
    webhook_secret: str | None = None

    # Surfaced by /api/version for provenance: VERSION (the Modal deploy sets the git sha), else the release.
    version: str = __version__

    # LOCAL backends (the server's `claude` CLI subscription, local Ollama) spend the HOST's own
    # resources, so they are OFF by default: a public server must never let arbitrary visitors drive
    # its subscription. Enable only for a local, single-user server (launch.json does this); CORS is
    # then restricted to `cors_origins`.
    allow_local_backends: bool = Field(
        default=False,
        validation_alias=AliasChoices("FUSION_ALLOW_LOCAL_BACKENDS", "allow_local_backends"),
    )
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


def load_settings() -> Settings:
    return Settings()
