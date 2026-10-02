"""JSON-returning agent tools wrapped by the MCP server and CLI.

The tools resolve lazily (PEP 562) so importing `claude_hooks`, which runs before every Claude Code
tool call, does not load the scan engine."""

from __future__ import annotations

import importlib

_AGENT_TOOLS = (
    "check_output",
    "check_tool_call",
    "guardrail_snippet",
    "harden_prompt",
    "list_checks",
    "scan_prompt",
)

__all__ = [
    "list_checks",
    "scan_prompt",
    "harden_prompt",
    "guardrail_snippet",
    "check_output",
    "check_tool_call",
]


def __getattr__(name: str):
    if name in _AGENT_TOOLS:
        value = getattr(importlib.import_module("fusion_first.integrations.agent_tools"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
