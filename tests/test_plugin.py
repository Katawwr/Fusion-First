"""The Claude Code plugin stays consistent with the code it drives: manifest shape, the MCP launch
command, the judge agent's tool allowlist, and every tool a skill tells Claude to call."""

from __future__ import annotations

import json
import pathlib
import re
import tomllib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "fusion"
SERVER = "fusion"  # key in plugins/fusion/.mcp.json
TOOL_PREFIX = f"mcp__plugin_fusion_{SERVER}__"


def _mcp_tool_names() -> set[str]:
    """The tools mcp_server.build_server registers (parsed, so the test doesn't need the SDK)."""
    src = (ROOT / "fusion/integrations/mcp_server.py").read_text(encoding="utf-8")
    return set(re.findall(r"@mcp\.tool\(\)\s+(?:async\s+)?def\s+(\w+)\(", src))


def _frontmatter(path: pathlib.Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))  # CRLF checkouts
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path} has no frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


@pytest.mark.unit
def test_manifest_and_marketplace():
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "fusion" and manifest["version"] and manifest["description"]
    # Keys the installed `claude plugin validate` accepts (it rejects unknown keys).
    assert set(manifest) <= {"name", "version", "description", "author", "homepage", "repository",
                             "license", "keywords"}
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    for entry in market["plugins"]:
        src = ROOT / entry["source"]
        assert (src / ".claude-plugin/plugin.json").exists(), entry
        assert json.loads((src / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["name"] == entry["name"]


@pytest.mark.unit
def test_mcp_launch_command_matches_the_package():
    cfg = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][SERVER]
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert cfg["command"] == "uvx"
    assert cfg["args"][-1] in scripts and scripts[cfg["args"][-1]].startswith("fusion.integrations.mcp_server")
    assert not any(k.upper().endswith(("API_KEY", "TOKEN")) for k in cfg.get("env", {}))  # keyless


@pytest.mark.unit
def test_judge_agent_is_restricted_to_grading_tools():
    meta, body = _frontmatter(PLUGIN / "agents/fusion-judge.md")
    tools = [t.strip() for t in meta["tools"].split(",")]
    assert all(t.startswith(TOOL_PREFIX) for t in tools), tools
    names = {t[len(TOOL_PREFIX):] for t in tools}
    assert names == {"get_grading_tasks", "submit_grades", "run_status"}
    assert names <= _mcp_tool_names()
    assert "untrusted" in body and "Never follow instructions" in body


@pytest.mark.unit
def test_skills_only_call_tools_that_exist():
    tools = _mcp_tool_names()
    skills = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
    assert {p.parent.name for p in skills} >= {"audit", "grade", "harden", "setup", "guard"}
    for path in skills:
        meta, body = _frontmatter(path)
        assert meta["name"] == path.parent.name and len(meta["description"]) > 40
        called = set(re.findall(r"`([a-z][a-z_]+)\(", body))
        assert called <= tools, f"{path.parent.name} calls unknown tools: {called - tools}"


@pytest.mark.integration
def test_mcp_server_speaks_stdio(tmp_path):
    """A real MCP handshake over stdio with the server as a subprocess (offline)."""
    pytest.importorskip("mcp")
    import asyncio
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        env = {**os.environ, "FUSION_OFFLINE": "1", "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)}
        params = StdioServerParameters(command=sys.executable, args=["-m", "fusion.integrations.mcp_server"],
                                       env=env, cwd=str(tmp_path))
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            listed = {t.name for t in (await s.list_tools()).tools}
            doc = json.loads((await s.call_tool("fusion_doctor", {"check_auth": False})).content[0].text)
            runs = json.loads((await s.call_tool("list_runs", {})).content[0].text)
            return listed, doc, runs

    listed, doc, runs = asyncio.run(asyncio.wait_for(go(), timeout=90))
    assert listed == _mcp_tool_names()
    assert doc["zero_spend"] is True and runs == {"runs": []}
