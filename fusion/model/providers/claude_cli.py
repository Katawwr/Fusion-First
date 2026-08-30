"""Subscription-backed Claude adapter via the `claude` CLI — real models with NO API key.

This is the build/test-phase retrofit that turns the offline demo into real numbers when an
`ANTHROPIC_API_KEY` is not available but the developer has the `claude` CLI (a Claude subscription).
It runs `claude -p ... --output-format json` as a subprocess, so the real target + judge +
cassette-recording all work against live models. Everything downstream (the judge parser, the
stats, the gate) is unchanged — this is just another `ModelClient`.

Design notes that are load-bearing:
  * The nested-session guard (`CLAUDECODE` et al.) is unset for the child so a headless `-p` call
    can launch from inside another Claude Code session.
  * `--system-prompt` REPLACES the default system prompt and `--setting-sources ""` skips project
    CLAUDE.md/settings; run in a fresh temp cwd → ~600-token hidden overhead (a fair clean call).
  * A JUDGE request carries `model_id=None` (the cassette-key linchpin — see judge.py). The client
    therefore chooses the actual judge tier via `judge_model` WITHOUT touching the request, so a
    stronger tier can grade a weaker target (independence) while cassette keys stay stable.
  * Kept modal-free and SDK-free (stdlib only) so importing `fusion` never requires the CLI to exist.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile

from fusion.model.client import ModelRequest, ModelResponse, ModelRole
from fusion.model.providers._common import resolve_model
from fusion.model.registry import ModelRegistry

_ROLE_MAP = {
    ModelRole.JUDGE: "judge_primary",
    ModelRole.CALIBRATION: "judge_calibration",
    ModelRole.PREFILTER: "judge_prefilter",
    # TARGET intentionally absent — a target model must be named explicitly (model_id).
}

# Allowlist id -> a concrete CLI model string. Anthropic ids only; OpenAI cannot be served here.
# Verified: `claude-sonnet-5` and `claude-haiku-4-5-20251001` resolve as CLI model names.
_CLI_MODEL_MAP = {
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-opus-4-8": "claude-opus-4-8",
}

# Env vars that make a nested `claude -p` refuse to launch; unset them for the child process.
_GUARD_ENV_VARS = ("CLAUDECODE", "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_ENTRYPOINT")


class ClaudeCliUnavailable(RuntimeError):
    """The `claude` CLI cannot serve a request (binary missing, non-Claude model, or a CLI error)."""


def claude_cli_available(binary: str | None = None) -> bool:
    """True if a `claude` binary can be located (PATH or FUSION_CLAUDE_BIN)."""
    return bool(binary or os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude"))


class ClaudeCliModelClient:
    """A ModelClient backed by the `claude` CLI subprocess (subscription auth, no API key)."""

    def __init__(
        self,
        *,
        binary: str | None = None,
        registry: ModelRegistry | None = None,
        judge_model: str | None = None,
        timeout: float = 90.0,
        max_retries: int = 1,
        clean_cwd: str | None = None,
    ):
        self._binary = binary
        self._registry = registry or ModelRegistry()
        # Override the role-default judge tier (e.g. opus judging a haiku target) WITHOUT changing
        # the request's cache key — the request still carries model_id=None. Must be allowlisted.
        self._judge_model = judge_model
        self._timeout = timeout
        self._max_retries = max_retries
        self._clean_cwd = clean_cwd  # if None, a fresh temp dir is created per call

    # -- pure helpers (unit-testable without spawning a subprocess) ----------------------------

    def _resolve_binary(self) -> str:
        b = self._binary or os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude")
        if not b:
            raise ClaudeCliUnavailable("`claude` CLI not found on PATH (set FUSION_CLAUDE_BIN)")
        return b

    def _cli_model(self, request: ModelRequest) -> str:
        """Resolve the allowlist id for this request, then map it to a CLI model string."""
        judge_role = request.role in (ModelRole.JUDGE, ModelRole.CALIBRATION)
        if self._judge_model and judge_role and request.model_id is None:
            self._registry.require_allowed(self._judge_model)
            allow_id = self._judge_model
        else:
            allow_id = resolve_model(self._registry, request, _ROLE_MAP)
        cli = _CLI_MODEL_MAP.get(allow_id)
        if cli is None:
            raise ClaudeCliUnavailable(f"model '{allow_id}' cannot be served by the claude CLI")
        return cli

    @staticmethod
    def _flatten_messages(messages: list[dict]) -> str:
        """A single user turn is sent verbatim; a multi-turn conversation is rendered as a labeled
        transcript so a stateless `-p` call still carries context (the judge reads the whole
        trajectory anyway)."""
        if len(messages) == 1 and messages[0].get("role") == "user":
            return messages[0].get("content", "")
        lines = []
        for m in messages:
            role = str(m.get("role", "user")).capitalize()
            lines.append(f"{role}: {m.get('content', '')}")
        return "\n\n".join(lines)

    def _build_argv(self, binary: str, request: ModelRequest, cli_model: str) -> list[str]:
        system = request.system
        if request.response_schema is not None:
            # Nudge bare-JSON output; does NOT change the cache key (computed upstream from the
            # unmodified request), only improves parse reliability. The judge tolerates fences too.
            system = (system + "\n\nReturn ONLY the JSON object — no prose, no markdown fences.").strip()
        return [
            binary,
            "-p",
            self._flatten_messages(request.messages),
            "--model",
            cli_model,
            "--system-prompt",
            system,
            "--tools",
            "",
            "--setting-sources",
            "",
            "--output-format",
            "json",
        ]

    @staticmethod
    def _build_env() -> dict:
        env = os.environ.copy()
        for var in _GUARD_ENV_VARS:
            env.pop(var, None)
        return env

    @staticmethod
    def _parse_cli_json(stdout: str, cli_model: str) -> ModelResponse:
        data = json.loads(stdout)
        if data.get("is_error"):
            raise ClaudeCliUnavailable(f"claude CLI error: {str(data.get('result'))[:200]}")
        usage = data.get("usage", {}) or {}
        return ModelResponse(
            text=data.get("result", "") or "",
            model=cli_model,
            input_tokens=usage.get("input_tokens", 0) or 0,
            output_tokens=usage.get("output_tokens", 0) or 0,
            stop_reason="cli",
        )

    # -- the ModelClient contract --------------------------------------------------------------

    async def complete(self, request: ModelRequest) -> ModelResponse:
        binary = self._resolve_binary()
        cli_model = self._cli_model(request)  # raises ClaudeCliUnavailable early (non-retryable)
        argv = self._build_argv(binary, request, cli_model)
        env = self._build_env()

        last_exc: Exception | None = None
        for _ in range(self._max_retries + 1):
            cwd = self._clean_cwd or tempfile.mkdtemp(prefix="fusion_cli_")
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )
                out, err = await asyncio.wait_for(proc.communicate(), self._timeout)
                if proc.returncode != 0:
                    raise ClaudeCliUnavailable(
                        f"claude CLI exited {proc.returncode}: "
                        f"{err.decode('utf-8', 'replace')[:200]}"
                    )
                return self._parse_cli_json(out.decode("utf-8", "replace"), cli_model)
            except (TimeoutError, json.JSONDecodeError, ClaudeCliUnavailable) as exc:
                last_exc = exc
                if proc is not None and proc.returncode is None:
                    try:
                        proc.kill()
                        # Reap the child so it releases the temp cwd before finally's rmtree (on
                        # Windows a still-running process holds its cwd and rmtree would silently fail).
                        await asyncio.wait_for(proc.wait(), 5)
                    except (ProcessLookupError, TimeoutError):
                        pass
            finally:
                if self._clean_cwd is None:
                    shutil.rmtree(cwd, ignore_errors=True)
        raise ClaudeCliUnavailable(
            f"claude CLI failed after {self._max_retries + 1} attempt(s): {last_exc}"
        )
