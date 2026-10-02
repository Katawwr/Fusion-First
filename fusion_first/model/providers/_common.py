"""Shared helpers for the live provider adapters (no SDK imports)."""

from __future__ import annotations

from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.registry import ModelRegistry


def strictify_schema(schema: dict) -> dict:
    """A copy of the schema with `additionalProperties: false` and `required` on every object."""
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    node_type = out.get("type")
    if node_type == "object":
        props = out.get("properties", {})
        out["properties"] = {k: strictify_schema(v) for k, v in props.items()}
        out["additionalProperties"] = False
        out.setdefault("required", list(props.keys()))
    elif node_type == "array" and "items" in out:
        out["items"] = strictify_schema(out["items"])
    return out


def resolve_model(registry: ModelRegistry, request: ModelRequest, role_map: dict[ModelRole, str]) -> str:
    """An explicit allowlisted `model_id` wins; else the role's registry default (TARGET has none)."""
    if request.model_id:
        registry.require_allowed(request.model_id)
        return request.model_id
    key = role_map.get(request.role)
    if key is None:
        raise ValueError(f"role {request.role.value} requires an explicit model_id")
    return registry.resolve(key)


def is_bad_request(exc: Exception) -> bool:
    """Best-effort HTTP 400 detection (falls back from strict schema to plain JSON)."""
    return getattr(exc, "status_code", None) == 400 or "BadRequest" in type(exc).__name__
