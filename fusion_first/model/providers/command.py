"""Any program as the model under test (or as a grader): Fusion writes one JSON request to the
command's stdin and reads the reply from its stdout. A few lines wrap a LangChain chain, a
transformers pipeline, a call to your own agent's HTTP API, or anything else.

  stdin   {"system": "...", "messages": [{"role": "user", "content": "..."}, ...],
           "max_tokens": 512, "temperature": 0.0, "role": "target" | "judge" | ...}
  stdout  the reply as plain text, or {"text": "..."}; a non-zero exit is an error.

Runs without a shell. The command has the user's own permissions, so the MCP server refuses command
targets unless FUSION_ALLOW_CMD_TARGETS=1.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import time

from fusion_first.errors import FusionProviderError
from fusion_first.model.client import ModelRequest, ModelResponse
from fusion_first.offline import offline

ALLOW_REMOTE_ENV = "FUSION_ALLOW_CMD_TARGETS"


class CommandTargetError(FusionProviderError):
    """The command could not run, failed, or timed out."""


def remote_commands_allowed() -> bool:
    """May a command target come from outside the CLI (an agent over MCP)? Only if the user said so."""
    return os.environ.get(ALLOW_REMOTE_ENV) == "1"


def command_argv(command: str) -> list[str]:
    if os.name == "nt":  # POSIX rules would eat the backslashes of Windows paths
        parts = shlex.split(command, posix=False)
        return [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]
    return shlex.split(command)


class CommandModelClient:
    def __init__(self, command: str, *, timeout: float = 600.0):
        self._command = command
        self._argv = command_argv(command)
        if not self._argv:
            raise ValueError("empty command")
        self._timeout = timeout

    def _run(self, payload: dict) -> str:
        try:
            proc = subprocess.run(self._argv, input=json.dumps(payload), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=self._timeout)
        except FileNotFoundError as e:
            raise CommandTargetError(f"command not found: {self._argv[0]}") from e
        except subprocess.TimeoutExpired as e:
            raise CommandTargetError(f"command timed out after {self._timeout:.0f}s: {self._command}") from e
        except OSError as e:
            raise CommandTargetError(f"could not run {self._command}: {e}") from e
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-300:]
            raise CommandTargetError(f"command exited with {proc.returncode}: {tail}")
        return proc.stdout

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if offline():
            raise CommandTargetError("FUSION_OFFLINE=1: real model calls are disabled")
        started = time.monotonic()
        payload = {"system": request.system or "", "messages": list(request.messages),
                   "max_tokens": request.max_tokens, "temperature": request.temperature,
                   "role": request.role.value}
        text = (await asyncio.to_thread(self._run, payload)).strip()
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            text = data["text"]  # {"text": ...}; any other JSON (a judge verdict) passes through whole
        return ModelResponse(text=text, model=f"cmd:{self._command}", latency_s=round(time.monotonic() - started, 3))
