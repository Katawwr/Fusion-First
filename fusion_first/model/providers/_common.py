"""Shared helpers for the live provider adapters (no SDK imports)."""

from __future__ import annotations

import json

from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.registry import ModelRegistry


def normalize_tool_calls(raw: object) -> list[dict] | None:
    """Provider tool calls (OpenAI or Ollama shape, `[{"function": {"name", "arguments"}}]`) as
    `[{"name": str, "arguments": dict}]`. String arguments are JSON-decoded; text that does not decode
    to a JSON object (undecodable, or a list, string, number, ...) gives `arguments = {}` plus the text
    as `"arguments_raw"`; other non-dict arguments give `{}`; a call without a name is skipped. None
    when there is no usable call."""
    if not isinstance(raw, list):
        return None
    out: list[dict] = []
    for call in raw:
        fn = call.get("function") if isinstance(call, dict) else None
        if not isinstance(fn, dict) or not isinstance(fn.get("name"), str) or not fn["name"]:
            continue
        args = fn.get("arguments")
        entry: dict = {"name": fn["name"], "arguments": {}}
        if isinstance(args, str):
            text = args
            try:
                args = json.loads(text)
            except json.JSONDecodeError:
                args = None
            if not isinstance(args, dict):
                entry["arguments_raw"] = text
        if isinstance(args, dict):
            entry["arguments"] = args
        out.append(entry)
    return out or None


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
