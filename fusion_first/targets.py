"""Any Python function as the model under test: `fn(system, messages) -> str`, sync or async.

    from fusion_first.runs import service
    from fusion_first.targets import FunctionModelClient

    rd = service.start_run(".", SYSTEM_PROMPT, target="python:my_bot", grader="claude-cli")
    await service.drive(rd, target_client=FunctionModelClient(my_bot))

`messages` is the chat so far ([{"role": "user", "content": ...}, ...]); the function returns the
agent's reply text, tool calls included as the agent writes them. Wrap whatever the agent really runs
on (a framework chain, a local transformers model, an HTTP call) so the test exercises it end to end.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable

from fusion_first.model.client import ModelRequest, ModelResponse


class FunctionModelClient:
    def __init__(self, fn: Callable, *, name: str = "python"):
        self._fn = fn
        self._name = name

    async def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.monotonic()
        out = self._fn(request.system or "", list(request.messages))
        if inspect.isawaitable(out):
            out = await out
        if not isinstance(out, str):
            raise TypeError(f"the target function must return a str, got {type(out).__name__}")
        return ModelResponse(text=out, model=self._name, latency_s=round(time.monotonic() - started, 3))
