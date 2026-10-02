"""Runtime settings from the environment. Keys stay server-side and are never returned."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from fusion_first import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    target_model: str = "claude-haiku-4-5"
    scan_max_calls: int = 400  # per-scan model-call ceiling (BudgetedModelClient)
    prompt_max_chars: int = 32_000
    sse_heartbeat_s: float = 15.0
    # VERSION env (the Modal deploy sets the git sha), else the release.
    version: str = __version__

    # Local backends (claude CLI subscription, Ollama) spend the host's resources: off by default so
    # a public server never lets visitors drive them. When on, CORS is limited to `cors_origins`.
    allow_local_backends: bool = Field(
        default=False,
        validation_alias=AliasChoices("FUSION_ALLOW_LOCAL_BACKENDS", "allow_local_backends"),
    )
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


def load_settings() -> Settings:
    return Settings()
