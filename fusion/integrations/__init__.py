"""Integration surface: pure, JSON-returning tools that let an AI coding agent (or a CI pipeline,
or any host) use Fusion to FIND prompt/agent-safety issues, FIX them, and PROTECT at runtime.

Nothing here imports `modal`; the MCP server and CLI wrap these functions."""

from fusion.integrations.agent_tools import (
    check_output,
    check_tool_call,
    guardrail_snippet,
    harden_prompt,
    list_checks,
    scan_prompt,
)

__all__ = [
    "list_checks",
    "scan_prompt",
    "harden_prompt",
    "guardrail_snippet",
    "check_output",
    "check_tool_call",
]
