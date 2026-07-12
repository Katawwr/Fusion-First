"""Fusion First MCP server — expose the find / fix / protect loop to any MCP client.

Point an AI coding agent (Claude Code, Cursor, Windsurf, …) at this server and it can, mid-build,
grade the system prompt it just wrote, apply the fix, and gate the agent's outputs and tool calls
at runtime — without leaving the editor.

    pip install "fusion-safety[mcp]"
    python -m fusion.integrations.mcp_server        # stdio transport

Claude Code / Cursor MCP config (stdio):
    {
      "mcpServers": {
        "fusion-safety": { "command": "python", "args": ["-m", "fusion.integrations.mcp_server"] }
      }
    }

The `mcp` SDK is imported lazily inside build_server() so importing this module never requires the
extra — the underlying tools (fusion.integrations.agent_tools) are pure and tested on their own.
"""

from __future__ import annotations

from fusion.integrations import agent_tools as t

_INSTRUCTIONS = (
    "Fusion First tests, fixes, and protects AI agents against the OWASP LLM/Agentic safety risks "
    "(prompt injection, excessive agency, data exfiltration, system-prompt leakage). Workflow: call "
    "scan_prompt on a system prompt to FIND issues, harden_prompt to FIX it, and use check_output / "
    "check_tool_call to PROTECT the running agent. scan_prompt returns DEMONSTRATION numbers offline."
)


def build_server():
    """Construct the FastMCP server. Requires the `mcp` extra (`pip install fusion-safety[mcp]`)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as e:  # pragma: no cover - depends on optional extra
        raise SystemExit(
            "The Fusion MCP server needs the 'mcp' extra. Install it with:\n"
            "    pip install \"fusion-safety[mcp]\""
        ) from e

    mcp = FastMCP("fusion-safety", instructions=_INSTRUCTIONS)

    @mcp.tool()
    def list_checks() -> dict:
        """List the safety checks Fusion can run, with their OWASP mapping and what 'safe' means."""
        return t.list_checks()

    @mcp.tool()
    async def scan_prompt(system_prompt: str, checks: list[str] | None = None, tier: str = "quick", live: bool = False) -> dict:
        """FIND issues: grade a system prompt against the safety checks. Returns per-check grades,
        the baseline->hardened issue-rate reduction, the honesty badge, and the concrete attacks
        that got through. Offline DEMONSTRATION numbers by default; live=True grades the real prompt
        via a model (needs ANTHROPIC_API_KEY)."""
        return await t.scan_prompt(system_prompt, checks, tier, live)

    @mcp.tool()
    def harden_prompt(system_prompt: str, checks: list[str] | None = None) -> dict:
        """FIX: return the system prompt with Fusion's tested guard rules appended (idempotent),
        plus the guard block on its own. Paste the hardened prompt back into your agent."""
        return t.harden_prompt(system_prompt, checks)

    @mcp.tool()
    def guardrail_snippet(checks: list[str] | None = None) -> dict:
        """PROTECT: the copy-paste runtime-guardrail code (Python) to wrap your model client with."""
        return t.guardrail_snippet(checks)

    @mcp.tool()
    def check_output(text: str, secret_values: list[str] | None = None, system_prompt: str | None = None, on_secret: str = "redact") -> dict:
        """PROTECT (runtime): decide whether a model response is safe to return. Blocks/redacts leaked
        secrets, PII, and system-prompt reproductions; returns the safe text to send instead."""
        return t.check_output(text, secret_values, system_prompt, on_secret)

    @mcp.tool()
    def check_tool_call(name: str, arguments: dict, user_request: str = "", allowlisted_domains: list[str] | None = None, secret_values: list[str] | None = None, require_authorization: bool = True) -> dict:
        """PROTECT (runtime): decide whether a tool call is safe to execute. Blocks unauthorized
        consequential actions, sends to external/untrusted destinations, and secret/PII exfiltration."""
        return t.check_tool_call(name, arguments, user_request, allowlisted_domains, secret_values, require_authorization)

    return mcp


def main() -> None:  # pragma: no cover - transport entry point
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
