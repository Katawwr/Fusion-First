"""Shared helpers for the live provider adapters (schema strictification, model resolution).

Kept tiny and dependency-free (no SDK imports) so the adapters stay easy to unit-test with fakes.
"""

from __future__ import annotations

from fusion.model.client import ModelRequest, ModelRole
from fusion.model.registry import ModelRegistry


def strictify_schema(schema: dict) -> dict:
    """Return a copy of a JSON schema that satisfies structured-output strictness rules:
    every object gets `additionalProperties: false` and an explicit `required` list."""
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
    """Resolve the concrete model id: an explicit `model_id` (checked against the allowlist) wins;
    otherwise the request's role maps to a registry role key. TARGET has no default — the caller
    must name the model under test."""
    if request.model_id:
        registry.require_allowed(request.model_id)
        return request.model_id
    key = role_map.get(request.role)
    if key is None:
        raise ValueError(f"role {request.role.value} requires an explicit model_id")
    return registry.resolve(key)


def is_bad_request(exc: Exception) -> bool:
    """Best-effort detection of an HTTP 400 (used to fall back from strict schema to plain JSON)."""
    return getattr(exc, "status_code", None) == 400 or "BadRequest" in type(exc).__name__
