"""Any Python function as the model under test: `fn(system, messages) -> str`, sync or async.

    from fusion_first.runs import service
    from fusion_first.targets import FunctionModelClient

    rd = service.start_run(".", SYSTEM_PROMPT, target="python:my_bot", grader="claude-cli")
    await service.drive(rd, target_client=FunctionModelClient(my_bot))

`messages` is the chat so far ([{"role": "user", "content": ...}, ...]); the function returns the
agent's reply text, tool calls included as the agent writes them. Wrap whatever the agent really runs
on (a framework chain, a local transformers model, an HTTP call) so the test exercises it end to end.

For a tool-loop scan, take a third parameter: `fn(system, messages, tools)`. `tools` is the list of OpenAI
function schemas offered (None when none are), `messages` then also holds the assistant's earlier tool calls
and the scripted tool results, and the function returns `{"text": ..., "tool_calls": [{"name": ...,
"arguments": {...}}]}` (`[]` when it calls none). Fusion never executes a call. A two-parameter function
ignores tools, and a tool-loop scan of it stops.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable

from fusion_first.model.client import ModelRequest, ModelResponse
from fusion_first.model.providers._common import agent_tool_calls


class FunctionModelClient:
    def __init__(self, fn: Callable, *, name: str = "python"):
        self._fn = fn
        self._name = name
        try:
            params = [p for p in inspect.signature(fn).parameters.values()
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)]
        except (TypeError, ValueError):
            params = []
        self._takes_tools = len(params) >= 3 or any(p.kind == p.VAR_POSITIONAL for p in params)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.monotonic()
        args = (request.system or "", list(request.messages))
        out = self._fn(*args, request.tools) if self._takes_tools else self._fn(*args)
        if inspect.isawaitable(out):
            out = await out
        calls = None
        if self._takes_tools and request.tools is not None and isinstance(out, dict) and "tool_calls" in out:
            calls = agent_tool_calls(out["tool_calls"])
            out = out.get("text") or ""
        if not isinstance(out, str):
            raise TypeError(f"the target function must return a str, got {type(out).__name__}")
        return ModelResponse(text=out, model=self._name, tool_calls=calls,
                             latency_s=round(time.monotonic() - started, 3))
