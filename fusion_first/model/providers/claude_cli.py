"""Claude via the `claude` CLI on subscription auth (`claude -p ... --output-format json`), no API key.

- The nested-session guard env vars are unset so `-p` can launch inside another Claude Code session.
- `--system-prompt` replaces the default prompt; `--setting-sources ""` and a fresh temp cwd keep
  the call clean.
- `judge_model` picks the judge tier without touching the request, so cassette keys stay stable.
- Zero spend: paid-auth env vars are stripped from every child, and `assert_subscription_auth` refuses
  any call unless `claude auth status` reports subscription auth.
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

from fusion_first.errors import (
    FatalRunError,
    FusionProviderError,
    PromptTooLong,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderTimeout,
)
from fusion_first.model.client import ModelRequest, ModelResponse, ModelRole
from fusion_first.model.providers._common import resolve_model
from fusion_first.model.registry import ModelRegistry
from fusion_first.offline import offline

_ROLE_MAP = {
    ModelRole.JUDGE: "judge_primary",
    ModelRole.CALIBRATION: "judge_calibration",
    ModelRole.PREFILTER: "judge_prefilter",
    # TARGET absent: a target model must be named explicitly (model_id).
}

# Allowlist id -> CLI model string (Anthropic ids only).
_CLI_MODEL_MAP = {
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-opus-4-8": "claude-opus-4-8",
}

# Env vars that make a nested `claude -p` refuse to launch; unset them for the child process.
_GUARD_ENV_VARS = ("CLAUDECODE", "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_ENTRYPOINT")

# Env vars that would route a child `claude` call to metered auth; stripped from every child.
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
AUTH_TTL_S = 60.0  # a long-lived server notices an auth switch quickly


class ClaudeCliUnavailable(FusionProviderError):
    """The `claude` CLI cannot serve a request (binary missing, non-Claude model, or a CLI error)."""


class PaidAuthRefused(ClaudeCliUnavailable, FatalRunError):
    """The CLI is not on subscription auth, so the call is refused (nothing can be metered)."""


def _child_env() -> dict:
    env = os.environ.copy()
    for var in (*_GUARD_ENV_VARS, *_PAID_AUTH_ENV_VARS):
        env.pop(var, None)
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process and its children (a hung child would otherwise hold the output open)."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True, check=False, timeout=10,
        )
    else:
        proc.kill()


def _run_bounded(argv: list[str], *, timeout: float, env: dict, **_ignored) -> subprocess.CompletedProcess:
    """Run a short command with a timeout enforced on Windows: output to temp files (no pipes a
    grandchild could hold open) and the whole tree killed on timeout."""
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

    A pass is cached per (binary, CLAUDE_CONFIG_DIR) for AUTH_TTL_S; refusals are never cached."""
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


_SHELL_SHIMS = (".cmd", ".bat")


def refuse_shell_shim(binary: str, os_name: str | None = None) -> None:
    """Refuse a Windows .cmd/.bat launcher: cmd.exe re-parses the `--system-prompt` argument, so a
    prompt with `"` and `&` could execute commands (BatBadBut) and a newline would cut it short."""
    if (os_name or os.name) == "nt" and str(binary).lower().endswith(_SHELL_SHIMS):
        raise ClaudeCliUnavailable(
            f"the claude CLI resolved to a shell shim ({binary}); Fusion won't pass untrusted prompts "
            "through cmd.exe. Install the native claude.exe (run `claude install`) or point "
            "FUSION_CLAUDE_BIN at it."
        )


def claude_cli_available(binary: str | None = None) -> bool:
    """A `claude` binary is found (PATH or FUSION_CLAUDE_BIN) and FUSION_OFFLINE is not set."""
    if offline():
        return False
    return bool(binary or os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude"))


def claude_cli_ready(binary: str | None = None, runner: Callable[..., object] | None = None) -> tuple[bool, str]:
    """(ready, reason): the CLI is found, calls are permitted and it is on subscription auth."""
    if not claude_cli_available(binary):
        return False, "the `claude` CLI isn't installed here (or FUSION_OFFLINE=1 is set)"
    b = binary or os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude") or "claude"
    try:
        assert_subscription_auth(b, runner=runner)
    except ClaudeCliUnavailable as e:
        return False, str(e)
    return True, "ok"


# Quota is checked first: a usage limit stops the run (never retried into overage); only
# transient throttling gets backoff.
_QUOTA_MARKERS = ("usage limit", "limit reached", "limit will reset", "resets at", "out of extra usage", "quota")
_RATE_MARKERS = ("rate limit", "rate_limit", "429", "529", "overloaded", "too many requests")

# Windows CreateProcess caps the whole command line at 32,767 chars; stay well under it.
ARGV_BUDGET = 30_000


class ClaudeCliRateLimited(ClaudeCliUnavailable, ProviderRateLimited):
    """Transient throttling, retried with backoff."""


class ClaudeCliQuotaExhausted(ClaudeCliUnavailable, ProviderQuotaExhausted):
    """The subscription usage limit was hit: the run stops, never retried."""


class ClaudeCliPromptTooLong(ClaudeCliUnavailable, PromptTooLong):
    """The request can't be passed to the CLI without exceeding the OS command-line limit."""


def classify_cli_error(text: str) -> ClaudeCliUnavailable:
    low = (text or "").lower()
    if any(m in low for m in _QUOTA_MARKERS):
        return ClaudeCliQuotaExhausted(f"claude CLI usage limit reached: {text[:200]}")
    if any(m in low for m in _RATE_MARKERS):
        return ClaudeCliRateLimited(f"claude CLI rate-limited: {text[:200]}")
    return ClaudeCliUnavailable(f"claude CLI error: {text[:200]}")


async def _kill_process_tree(proc) -> None:
    """Kill a CLI child and its descendants."""
    try:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), 10)
        else:
            proc.kill()
        await asyncio.wait_for(proc.wait(), 5)
    except (ProcessLookupError, TimeoutError, OSError):
        pass


class ClaudeCliModelClient:
    """A ModelClient backed by the `claude` CLI subprocess (subscription auth, no API key)."""

    # No temperature/max_tokens controls: repeat-run stability must be measured, not assumed.
    controls_sampling = False

    def __init__(
        self,
        *,
        binary: str | None = None,
        registry: ModelRegistry | None = None,
        judge_model: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        clean_cwd: str | None = None,
        sleep=None,
        backoff_base: float = 4.0,
    ):
        self._binary = binary
        self._registry = registry or ModelRegistry()
        # Overrides the role-default judge tier without changing the request's cache key. Allowlisted.
        self._judge_model = judge_model
        self._timeout = timeout
        self._max_retries = max_retries
        self._clean_cwd = clean_cwd  # None: a fresh temp dir per call
        self._sleep = sleep or asyncio.sleep
        self._backoff_base = backoff_base

    def _resolve_binary(self) -> str:
        b = self._binary or os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude")
        if not b:
            raise ClaudeCliUnavailable("`claude` CLI not found on PATH (set FUSION_CLAUDE_BIN)")
        refuse_shell_shim(b)
        return b

    def _cli_model(self, request: ModelRequest) -> str:
        """The allowlist id for this request, mapped to a CLI model string."""
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
        """A single user turn verbatim; a multi-turn conversation as a labelled transcript."""
        if len(messages) == 1 and messages[0].get("role") == "user":
            return messages[0].get("content", "")
        lines = []
        for m in messages:
            role = str(m.get("role", "user")).capitalize()
            lines.append(f"{role}: {m.get('content', '')}")
        return "\n\n".join(lines)

    def _build_argv(self, binary: str, request: ModelRequest, cli_model: str) -> list[str]:
        """The command line without the prompt, which goes over stdin."""
        system = request.system
        if request.response_schema is not None:
            # Nudge bare-JSON output; the cache key is computed upstream from the unmodified request.
            system = (system + "\n\nReturn ONLY the JSON object — no prose, no markdown fences.").strip()
        return [
            binary,
            "-p",
            "--model",
            cli_model,
            "--system-prompt",
            system,
            "--tools",
            "",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--output-format",
            "json",
        ]

    @staticmethod
    def _check_argv_budget(argv: list[str]) -> None:
        length = len(subprocess.list2cmdline(argv))
        if length > ARGV_BUDGET:
            raise ClaudeCliPromptTooLong(
                f"system prompt too long for the claude CLI command line ({length} > {ARGV_BUDGET} "
                "chars); use the Ollama backend for very long prompts"
            )

    @staticmethod
    def _build_env() -> dict:
        return _child_env()

    @staticmethod
    def _parse_cli_json(stdout: str, cli_model: str) -> ModelResponse:
        data = json.loads(stdout)
        if data.get("is_error"):
            raise classify_cli_error(str(data.get("result")))
        usage = data.get("usage", {}) or {}
        served = None
        model_usage = data.get("modelUsage")
        if isinstance(model_usage, dict) and model_usage:
            # The model that actually answered; provenance only.
            served = max(model_usage, key=lambda m: (model_usage[m] or {}).get("outputTokens", 0) or 0)
        return ModelResponse(
            text=data.get("result", "") or "",
            model=cli_model,
            input_tokens=usage.get("input_tokens", 0) or 0,
            output_tokens=usage.get("output_tokens", 0) or 0,
            stop_reason="cli",
            served_model=served,
        )

    def _backoff(self, attempt: int) -> float:
        # Deterministic jitter: 1.0x, 1.3x, 1.6x ...
        return self._backoff_base * (2 ** attempt) * (1.0 + 0.3 * (attempt % 3))

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if offline():
            raise ClaudeCliUnavailable("FUSION_OFFLINE=1: real model calls are disabled")
        binary = self._resolve_binary()
        cli_model = self._cli_model(request)
        argv = self._build_argv(binary, request, cli_model)
        self._check_argv_budget(argv)  # refuse up front, never a silently truncated prompt
        # Zero spend: verify subscription auth before calling.
        await asyncio.to_thread(assert_subscription_auth, binary)
        prompt = self._flatten_messages(request.messages)
        env = self._build_env()

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._run_once(argv, prompt, env, cli_model)
            except ClaudeCliQuotaExhausted:
                raise  # hard stop: never retry into overage
            except ClaudeCliRateLimited as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await self._sleep(self._backoff(attempt))
            except (ProviderTimeout, ClaudeCliUnavailable, json.JSONDecodeError) as exc:
                if getattr(exc, "spawn_failed", False):
                    raise  # the binary can't start; retrying won't help
                last_exc = exc
        if isinstance(last_exc, ClaudeCliRateLimited):
            raise last_exc
        if isinstance(last_exc, ProviderTimeout):
            raise ProviderTimeout(
                f"claude CLI timed out after {self._max_retries + 1} attempt(s) ({self._timeout:.0f}s each)"
            ) from last_exc
        raise ClaudeCliUnavailable(
            f"claude CLI failed after {self._max_retries + 1} attempt(s): {last_exc}"
        ) from last_exc

    async def _run_once(self, argv: list[str], prompt: str, env: dict, cli_model: str) -> ModelResponse:
        cwd = self._clean_cwd or tempfile.mkdtemp(prefix="fusion_cli_")
        proc = None
        started = time.monotonic()
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )
            except OSError as e:
                err = ClaudeCliUnavailable(f"could not start the claude CLI: {e}")
                err.spawn_failed = True  # type: ignore[attr-defined]
                raise err from e
            try:
                out, err_b = await asyncio.wait_for(
                    proc.communicate(prompt.encode("utf-8")), self._timeout
                )
            except TimeoutError as e:
                await _kill_process_tree(proc)
                raise ProviderTimeout(f"claude CLI call exceeded {self._timeout:.0f}s") from e
            stdout = out.decode("utf-8", "replace")
            if proc.returncode != 0:
                # The JSON envelope (with is_error) may still be on stdout; classify its message.
                try:
                    payload = json.loads(stdout)
                    message = str(payload.get("result", "")) if isinstance(payload, dict) else stdout
                except json.JSONDecodeError:
                    message = err_b.decode("utf-8", "replace") or stdout
                raise classify_cli_error(f"exit {proc.returncode}: {message}")
            resp = self._parse_cli_json(stdout, cli_model)
            return resp.model_copy(update={"latency_s": round(time.monotonic() - started, 3)})
        finally:
            if proc is not None and proc.returncode is None:
                await _kill_process_tree(proc)
            if self._clean_cwd is None:
                shutil.rmtree(cwd, ignore_errors=True)
