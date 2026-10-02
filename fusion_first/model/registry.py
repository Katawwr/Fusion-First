"""Model registry: roles to IDs, the allowlist, and the self-family judge guard."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml

_MODELS_YAML = pathlib.Path(__file__).with_name("models.yaml")


@dataclass(frozen=True)
class JudgeChoice:
    """A judge selection plus a disclosure of its independence from the target.

    `independence`: "cross_family", "same_family_cross_tier" or "same_model". `disclosure` is shown on
    the report card.
    """

    judge_id: str
    independence: str
    disclosure: str


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

    def _stronger_same_family(self, target_model_id: str) -> str:
        """The primary judge, escalated to the calibration tier when the target is the primary."""
        primary = self.resolve("judge_primary")
        if target_model_id != primary:
            return primary
        return self.resolve("judge_calibration")

    def choose_judge_with_disclosure(
        self, target_model_id: str, *, cross_family_available: bool = True
    ) -> JudgeChoice:
        """Pick a judge and disclose its independence: cross-family when callable, else a stronger
        same-family tier with the residual self-preference risk stated."""
        if cross_family_available:
            xf = self.resolve("judge_cross_family")
            if target_model_id not in self.allowlist or self.family_of(xf) != self.family_of(
                target_model_id
            ):
                return JudgeChoice(
                    xf,
                    "cross_family",
                    f"Independent judge: {xf} is a different model family than the target "
                    f"({target_model_id}).",
                )
        judge_id = self._stronger_same_family(target_model_id)
        if judge_id == target_model_id:
            return JudgeChoice(
                judge_id,
                "same_model",
                f"Judge and target are the same model ({judge_id}); self-preference bias is likely — "
                "rely on Bar A vs the independent oracle and the guardrail cross-check.",
            )
        return JudgeChoice(
            judge_id,
            "same_family_cross_tier",
            f"Judge {judge_id} and target {target_model_id} are both Anthropic models (different "
            "tiers); self-preference bias cannot be fully excluded — see Bar A vs the oracle and the "
            "guardrail cross-check.",
        )


def family_of(model_id: str) -> str:
    return ModelRegistry().family_of(model_id)
