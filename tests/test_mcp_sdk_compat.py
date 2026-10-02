"""The MCP server runs on the MCP SDK 1.x (FastMCP) and 2.x (renamed MCPServer, which also takes the
server's own version). Both majors can't be installed together, so here the SDK is a stand-in that records
how the server is built; tests/test_plugin.py drives the installed SDK over real stdio."""

from __future__ import annotations

import sys
import types

import pytest

import fusion_first
from fusion_first.integrations import mcp_server
from tests.test_plugin import _mcp_tool_names


class _Recorder:
    built: dict = {}

    def __init__(self, name, **kwargs):
        _Recorder.built = {"name": name, **kwargs, "tools": [], "fns": {}}

    def tool(self):
        def register(fn):
            _Recorder.built["tools"].append(fn.__name__)
            _Recorder.built["fns"][fn.__name__] = fn
            return fn
        return register


class _ToolError(Exception):
    """Stands in for mcp.server.mcpserver.exceptions.ToolError."""


def _sdk(monkeypatch, major: int) -> None:
    present, absent, cls = (("mcp.server.mcpserver", "mcp.server.fastmcp", "MCPServer") if major == 2
                            else ("mcp.server.fastmcp", "mcp.server.mcpserver", "FastMCP"))
    for parent in ("mcp", "mcp.server"):
        monkeypatch.setitem(sys.modules, parent, types.ModuleType(parent))
    sdk = types.ModuleType(present)
    setattr(sdk, cls, _Recorder)
    monkeypatch.setitem(sys.modules, present, sdk)
    monkeypatch.setitem(sys.modules, absent, None)  # importing it raises ModuleNotFoundError
    if major == 2:
        exceptions = types.ModuleType("mcp.server.mcpserver.exceptions")
        exceptions.ToolError = _ToolError
        monkeypatch.setitem(sys.modules, "mcp.server.mcpserver.exceptions", exceptions)


class _BrokenRuns:
    """A run engine whose calls fail the way a real one does for a user's mistake."""

    async def start_run(self, *_, **__):
        raise ValueError("Ollama has no model named not-a-model: run `ollama pull <model>` first")

    def get_grading_tasks(self, *_, **__):
        raise ValueError("no run in this workspace: start one with start_run")


@pytest.mark.unit
async def test_on_sdk_2_a_tool_error_keeps_its_message(monkeypatch):
    """2.x shows the client only `Error executing tool <name>` unless the tool raises its ToolError, and
    Fusion's errors say what to do next: they are re-raised as ToolError (1.x shows every message)."""
    _sdk(monkeypatch, 2)
    mcp_server.build_server(runs=_BrokenRuns())
    fns = _Recorder.built["fns"]

    with pytest.raises(_ToolError, match="ollama pull"):
        await fns["start_run"](system_prompt="p", target="ollama:not-a-model")
    with pytest.raises(_ToolError, match="start one with start_run"):
        fns["get_grading_tasks"]()


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_the_server_builds_on_both_sdk_majors(monkeypatch, major):
    _sdk(monkeypatch, major)

    mcp_server.build_server()

    built = _Recorder.built
    assert built["name"] == "fusion-safety" and built["instructions"]
    assert set(built["tools"]) == _mcp_tool_names()
    # 2.x reports the version it is given (else an empty string); 1.x has no such argument.
    assert built.get("version") == (fusion_first.__version__ if major == 2 else None)


@pytest.mark.unit
def test_without_the_sdk_the_server_says_how_to_install_it(monkeypatch):
    for name in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.mcpserver"):
        monkeypatch.setitem(sys.modules, name, None)

    with pytest.raises(SystemExit, match=r'pip install "fusion-safety\[mcp\]"'):
        mcp_server.build_server()


def test_on_the_installed_sdk_the_server_reports_fusions_version():
    # On 1.x the low-level server has no version unless set, and then reports the mcp package's own.
    pytest.importorskip("mcp")

    server = mcp_server.build_server()

    low = getattr(server, "_mcp_server", None) or getattr(server, "_lowlevel_server", None)
    assert low.create_initialization_options().server_version == fusion_first.__version__
