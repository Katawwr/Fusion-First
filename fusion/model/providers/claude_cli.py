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
  * ZERO-SPEND GUARANTEE: paid-auth env vars (API keys, gateways, Bedrock/Vertex) are stripped from
    every child, and `assert_subscription_auth` refuses to make any call unless `claude auth status`
    reports subscription auth (claude.ai, first-party). Real calls ride the subscription or not at all.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable

from fusion.errors import FatalRunError, FusionProviderError
from fusion.model.client import ModelRequest, ModelResponse, ModelRole
from fusion.model.providers._common import resolve_model
from fusion.model.registry import ModelRegistry
from fusion.offline import offline

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

# Env vars that would route a child `claude` call to METERED auth (API keys, gateways, cloud
# providers). Stripped from every child so a stray key in the shell can never turn a subscription
# call into a billed one.
_PAID_AUTH_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "OPENAI_API_KEY",
)

# (binary, config dir) -> monotonic time of the last verified subscription-auth PASS.
_AUTH_OK: dict[tuple[str, str], float] = {}
AUTH_TTL_S = 600.0  # re-verify every 10 minutes so a long-lived server notices an auth switch


class ClaudeCliUnavailable(FusionProviderError):
    """The `claude` CLI cannot serve a request (binary missing, non-Claude model, or a CLI error)."""


class PaidAuthRefused(ClaudeCliUnavailable, FatalRunError):
    """The CLI is not on subscription auth (e.g. an API key or cloud provider) — refused, so no
    call can be metered. Fix: `claude auth login` with a Claude subscription account."""


def _child_env() -> dict:
    env = os.environ.copy()
    for var in (*_GUARD_ENV_VARS, *_PAID_AUTH_ENV_VARS):
        env.pop(var, None)
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process AND its children (the npm `claude.cmd` shim spawns node under cmd.exe, and
    killing only the parent would leave a hung child holding the output open)."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True, check=False, timeout=10,
        )
    else:
        proc.kill()


def _run_bounded(argv: list[str], *, timeout: float, env: dict, **_ignored) -> subprocess.CompletedProcess:
    """Run a short command with a timeout that is actually enforced on Windows: output goes to temp
    files (no pipes a grandchild could keep open) and the whole process tree is killed on timeout."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(argv, stdout=out, stderr=err, stdin=subprocess.DEVNULL, env=env)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(
            argv, rc, out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")
        )


def assert_subscription_auth(binary: str, runner: Callable[..., object] | None = None) -> None:
    """Refuse unless `claude auth status` reports subscription auth (claude.ai + firstParty).

    A PASS is cached per (binary, CLAUDE_CONFIG_DIR) for AUTH_TTL_S; refusals are never cached.
    `runner` is injectable for tests; it defaults to a tree-killing bounded runner."""
    key = (binary, os.environ.get("CLAUDE_CONFIG_DIR", ""))
    verified = _AUTH_OK.get(key)
    if verified is not None and time.monotonic() - verified < AUTH_TTL_S:
        return
    run = runner or _run_bounded
    try:
        proc = run([binary, "auth", "status"], capture_output=True, text=True, timeout=30,
                   env=_child_env(), encoding="utf-8")
    except (OSError, subprocess.SubprocessError) as e:
        raise PaidAuthRefused(f"could not verify claude auth status: {e}") from e
    try:
        status = json.loads(getattr(proc, "stdout", "") or "")
    except json.JSONDecodeError:
        status = None
    if isinstance(status, dict) and status.get("loggedIn") is False:
        raise PaidAuthRefused(
            "the `claude` CLI is not logged in — run `claude auth login` with your Claude "
            "subscription account (no calls were made)"
        )
    if getattr(proc, "returncode", 1) != 0:
        raise PaidAuthRefused("`claude auth status` failed; refusing to make unverified calls")
    if status is None:
        raise PaidAuthRefused("`claude auth status` was not JSON; refusing unverified calls")
    ok = (
        isinstance(status, dict)
        and status.get("loggedIn") is True
        and status.get("authMethod") == "claude.ai"
        and status.get("apiProvider") == "firstParty"
    )
    if not ok:
        shown = (
            {k: status.get(k) for k in ("loggedIn", "authMethod", "apiProvider")}
            if isinstance(status, dict) else status
        )
        raise PaidAuthRefused(
            f"claude CLI is not on subscription auth ({shown}); refusing so nothing can be billed"
        )
    _AUTH_OK[key] = time.monotonic()


def claude_cli_available(binary: str | None = None) -> bool:
    """True if a `claude` binary can be located (PATH or FUSION_CLAUDE_BIN) and real calls are
    permitted (FUSION_OFFLINE is not set)."""
    if offline():
        return False
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
        return _child_env()

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
        if offline():
            raise ClaudeCliUnavailable("FUSION_OFFLINE=1: real model calls are disabled")
        binary = self._resolve_binary()
        cli_model = self._cli_model(request)  # raises ClaudeCliUnavailable early (non-retryable)
        # Zero-spend guarantee: verify subscription auth before calling (PASS cached for AUTH_TTL_S).
        await asyncio.to_thread(assert_subscription_auth, binary)
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
