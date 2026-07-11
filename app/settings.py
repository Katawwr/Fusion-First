"""Runtime settings, read from the environment (Modal secret in prod, plain env locally).

Keys live server-side only and are never returned to the client. When no provider key is present,
the app runs in demo mode — every scan is a clearly-badged demonstration.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # Provider keys (server-side only). Presence of ANTHROPIC_API_KEY enables real scans.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Scan execution knobs.
    target_model: str = "claude-haiku-4-5"  # cheap default for running the user's prompt live
    scan_max_calls: int = 400  # per-scan model-call ceiling (BudgetedModelClient)
    prompt_max_chars: int = 32_000

    # Freemium stub (real enforcement lands with persistence in M4).
    free_scans_per_day: int = 3

    # Fail-closed webhook (billing effect stubbed; the signature gate is real).
    webhook_secret: str | None = None

    # Surfaced by /api/version for provenance.
    version: str = "dev"

    @property
    def has_live_keys(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    return Settings()
