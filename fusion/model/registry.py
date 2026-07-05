"""Model registry: resolves roles to concrete IDs, enforces the allowlist, and applies the
self-family guard so a model is never the sole judge of its own family's output.
"""

from __future__ import annotations

import pathlib

import yaml

_MODELS_YAML = pathlib.Path(__file__).with_name("models.yaml")


class ModelRegistry:
    def __init__(self, config: dict | None = None):
        self._cfg = config or yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
        self.roles: dict[str, str] = self._cfg["roles"]
        self.allowlist: dict[str, str] = self._cfg["allowlist"]
        self.limits: dict[str, int] = self._cfg.get("limits", {})

    def resolve(self, role_key: str) -> str:
        model_id = self.roles.get(role_key)
        if model_id is None:
            raise KeyError(f"unknown role '{role_key}'")
        self.require_allowed(model_id)
        return model_id

    def require_allowed(self, model_id: str) -> None:
        if model_id not in self.allowlist:
            raise ValueError(f"model '{model_id}' is not on the allowlist")

    def family_of(self, model_id: str) -> str:
        self.require_allowed(model_id)
        return self.allowlist[model_id]

    def choose_judge(self, target_model_id: str, prefer: str = "judge_primary") -> str:
        """Pick a judge for a given target, honoring the self-family guard.

        If the preferred judge shares the target's family, fall back to the cross-family judge.
        This prevents self-preference bias (a model rating its own family too kindly).
        """
        preferred = self.resolve(prefer)
        if target_model_id in self.allowlist and self.family_of(preferred) == self.family_of(
            target_model_id
        ):
            return self.resolve("judge_cross_family")
        return preferred


def family_of(model_id: str) -> str:
    return ModelRegistry().family_of(model_id)
