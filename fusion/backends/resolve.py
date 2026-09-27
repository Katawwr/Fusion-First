"""One place that turns a target/grader SPEC string into a client — and reports what is available.

Specs are plain strings so they read the same on the CLI, in MCP tool calls and in CI config:

  target  ollama:<model>        a local open-weight model (free)            e.g. ollama:llama3.2:1b
          claude-cli:<model>    a Claude model over the `claude` CLI subscription (no API key)
          openai-compat:<url>#<model>
                                YOUR model server (vLLM, LM Studio, llama.cpp, Ollama /v1...), e.g.
                                openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct. Local and
                                private-network servers are free; a public endpoint may be a metered
                                API, so it needs FUSION_ALLOW_API_SPEND=1
          api:<model>           METERED — only with FUSION_ALLOW_API_SPEND=1 (never used by default)
          <model>               bare id: an allowlisted Claude id → claude-cli, anything else → ollama

  grader  host                  the calling agent grades (MCP get_grading_tasks / submit_grades)
          claude-cli[:<model>]  Claude over the CLI subscription (default: the judge_primary role)
          ollama-prob:<model>   the local probability judge (token log-probabilities)
          ollama:<model>        a local model answering the JSON rubric (weakest; measured in-run)

ZERO SPEND: nothing here ever selects a metered provider on its own. The claude CLI provider refuses
unless `claude auth status` reports subscription auth, and strips paid-auth env vars from the child.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fusion.integrations.live import METERED_OPT_IN_ENV, metered_allowed
from fusion.model.registry import ModelRegistry

TARGET_BACKENDS = ("ollama", "claude_cli", "openai_compat", "api")
GRADER_KINDS = ("host", "claude_cli", "ollama_prob", "ollama_json")

_TARGET_PREFIXES = {
    "ollama": "ollama",
    "claude-cli": "claude_cli",
    "claude_cli": "claude_cli",
    "cli": "claude_cli",
    "openai-compat": "openai_compat",
    "openai_compat": "openai_compat",
    "api": "api",
}
_GRADER_PREFIXES = {
    "claude-cli": "claude_cli",
    "claude_cli": "claude_cli",
    "cli": "claude_cli",
    "ollama-prob": "ollama_prob",
    "ollama_prob": "ollama_prob",
    "ollama": "ollama_json",
    "ollama-json": "ollama_json",
    "ollama_json": "ollama_json",
}


class BackendUnavailable(RuntimeError):
    """The requested backend can't be used here (not installed, offline, or not permitted)."""


class SpecError(ValueError):
    """A target/grader spec string could not be parsed."""


@dataclass(frozen=True)
class TargetSpec:
    backend: str  # ollama | claude_cli | openai_compat | api
    model: str
    base_url: str | None = None  # openai_compat only

    @property
    def label(self) -> str:
        if self.base_url:
            return f"{self.backend.replace('_', '-')}:{self.base_url}#{self.model}"
        return f"{self.backend.replace('_', '-')}:{self.model}"


@dataclass(frozen=True)
class GraderSpec:
    kind: str  # host | claude_cli | ollama_prob | ollama_json
    model: str | None = None

    @property
    def label(self) -> str:
        return self.kind if self.model is None else f"{self.kind}:{self.model}"

    @property
    def external(self) -> bool:
        return self.kind == "host"


def _split(spec: str, prefixes: dict[str, str]) -> tuple[str | None, str]:
    """('ollama', 'llama3.2:1b') for 'ollama:llama3.2:1b'. Only KNOWN prefixes split, because model
    ids contain colons themselves (llama3.2:1b)."""
    head, sep, rest = spec.partition(":")
    if sep and head.lower() in prefixes:
        return prefixes[head.lower()], rest.strip()
    if spec.lower() in prefixes:
        return prefixes[spec.lower()], ""
    return None, spec


def parse_target(spec: str, registry: ModelRegistry | None = None) -> TargetSpec:
    spec = (spec or "").strip()
    if not spec:
        raise SpecError("empty target spec (try ollama:llama3.2:1b)")
    backend, model = _split(spec, _TARGET_PREFIXES)
    if backend == "openai_compat":
        return _parse_openai_compat(spec, model)
    if backend is None:
        registry = registry or ModelRegistry()
        is_claude = registry.allowlist.get(model) == "anthropic"
        backend = "claude_cli" if is_claude else "ollama"
    if not model:
        raise SpecError(f"target '{spec}' names no model (e.g. {backend.replace('_', '-')}:<model>)")
    if backend == "ollama" and model.lower().startswith(("claude", "gpt-")):
        raise SpecError(f"'{model}' is a hosted model id, not an Ollama model")
    return TargetSpec(backend, model)


def _parse_openai_compat(spec: str, rest: str) -> TargetSpec:
    from urllib.parse import urlsplit

    url, sep, model = rest.rpartition("#")
    if not sep or not url or not model.strip():
        raise SpecError(f"target '{spec}' needs a server URL and a model: openai-compat:<url>#<model>, e.g. "
                        "openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct")
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SpecError(f"'{url}' is not an http(s) server URL")
    return TargetSpec("openai_compat", model.strip(), url.strip().rstrip("/"))


_PRIVATE_SUFFIXES = (".localhost", ".local", ".lan", ".internal", ".home.arpa", ".intranet")


def _private_endpoint(url: str) -> bool:
    """True for a server on this machine or a private network (no metered provider lives there)."""
    import ipaddress
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if host == "localhost" or host.endswith(_PRIVATE_SUFFIXES) or (host and "." not in host and ":" not in host):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def parse_grader(spec: str) -> GraderSpec:
    spec = (spec or "host").strip()
    if spec.lower() == "host":
        return GraderSpec("host")
    kind, model = _split(spec, _GRADER_PREFIXES)
    if kind is None:
        raise SpecError(
            f"unknown grader '{spec}' (use host, claude-cli[:model], ollama-prob:<model>, ollama:<model>)"
        )
    if kind in ("ollama_prob", "ollama_json") and not model:
        raise SpecError(f"grader '{spec}' needs a model, e.g. ollama-prob:qwen2.5:7b")
    return GraderSpec(kind, model or None)


def _cli_preflight() -> None:
    """Fail in seconds — before any collect — if the claude CLI isn't usable on subscription auth.
    (`claude auth status` is local; no model call. The provider re-checks before every call.)"""
    import shutil

    from fusion.model.providers.claude_cli import (
        assert_subscription_auth,
        claude_cli_available,
        refuse_shell_shim,
    )

    if not claude_cli_available():
        raise BackendUnavailable("the `claude` CLI isn't on PATH (or FUSION_OFFLINE=1 is set)")
    binary = os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude") or "claude"
    refuse_shell_shim(binary)
    assert_subscription_auth(binary)


def build_target_client(spec: TargetSpec, *, max_calls: int = 400, timeout: float = 600.0):
    """A budgeted client for the target under test. Refuses unavailable or unpermitted backends."""
    from fusion.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=max_calls)
    if spec.backend == "ollama":
        from fusion.model.providers.ollama import OllamaModelClient, ollama_available

        if not ollama_available():
            raise BackendUnavailable("Ollama isn't answering at 127.0.0.1:11434 — run `ollama serve`")
        return BudgetedModelClient(
            OllamaModelClient(model=spec.model, timeout=timeout), limits, enforce_allowlist=False
        )
    if spec.backend == "claude_cli":
        from fusion.model.providers.claude_cli import ClaudeCliModelClient

        registry = ModelRegistry()
        registry.require_allowed(spec.model)
        _cli_preflight()
        return BudgetedModelClient(ClaudeCliModelClient(registry=registry), limits)
    if spec.backend == "openai_compat":
        from fusion.model.providers.openai_compat import OpenAICompatModelClient

        if not _private_endpoint(spec.base_url or "") and not metered_allowed("api"):
            raise BackendUnavailable(
                f"{spec.base_url} is a public endpoint and may be a metered API, so it is off by default: "
                f"set {METERED_OPT_IN_ENV}=1 to allow it (local and private-network servers need nothing)")
        return BudgetedModelClient(OpenAICompatModelClient(spec.base_url, spec.model, timeout=timeout), limits,
                                   enforce_allowlist=False)
    if spec.backend == "api":
        raise BackendUnavailable(_metered_refusal())
    raise SpecError(f"unknown target backend '{spec.backend}'")


def build_grader_client(spec: GraderSpec, *, max_calls: int = 1000, timeout: float = 600.0):
    """A judge client for a BUILT-IN grader. `host` has no client: the calling agent grades."""
    from fusion.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=max_calls)
    if spec.kind == "host":
        raise SpecError("the host grader has no built-in client — grade via get_grading_tasks/submit_grades")
    if spec.kind == "claude_cli":
        from fusion.model.providers.claude_cli import ClaudeCliModelClient

        registry = ModelRegistry()
        judge_id = spec.model or registry.resolve("judge_primary")
        registry.require_allowed(judge_id)
        _cli_preflight()
        return BudgetedModelClient(ClaudeCliModelClient(registry=registry, judge_model=judge_id), limits)
    from fusion.model.providers.ollama import OllamaModelClient, ollama_available

    if not ollama_available():
        raise BackendUnavailable("Ollama isn't answering at 127.0.0.1:11434 — run `ollama serve`")
    ollama = BudgetedModelClient(
        OllamaModelClient(model=spec.model, timeout=timeout), limits, enforce_allowlist=False
    )
    if spec.kind == "ollama_prob":
        from fusion.judge.prob_judge import ProbabilityJudge, ProbJudgeClient

        return ProbJudgeClient(ProbabilityJudge(ollama, model_id=spec.model))
    return _PinnedModel(ollama, spec.model)


class _PinnedModel:
    """Send every judge request to one local model (Judge requests carry no model id)."""

    def __init__(self, inner, model: str):
        self.inner, self.model = inner, model

    async def complete(self, request):
        return await self.inner.complete(request.model_copy(update={"model_id": self.model}))


def _metered_refusal() -> str:
    if metered_allowed("api"):
        return "metered API targets aren't supported by the run engine; use ollama: or claude-cli:"
    return f"api: targets spend money on a metered key and are disabled (needs {METERED_OPT_IN_ENV}=1)"


# ------------------------------------------------------------------------------------ doctor


def doctor(*, check_auth: bool = True, auth_runner=None) -> dict:
    """What can run here, keyless. `check_auth` runs `claude auth status` (local, no model call)."""
    from fusion.model.providers.claude_cli import (
        ClaudeCliUnavailable,
        assert_subscription_auth,
        claude_cli_available,
    )
    from fusion.model.providers.ollama import ollama_available, ollama_models
    from fusion.offline import offline

    registry = ModelRegistry()
    cli = {"available": claude_cli_available(), "subscription": "not checked", "roles": ["target", "grader"]}
    if cli["available"] and check_auth:
        import os
        import shutil

        binary = os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude") or "claude"
        try:
            assert_subscription_auth(binary, runner=auth_runner)
            cli["subscription"] = "ok"
        except ClaudeCliUnavailable as e:
            cli["subscription"] = f"refused: {e}"
    cli_ok = cli["available"] and cli["subscription"] in ("ok", "not checked")

    models = [m["name"] for m in ollama_models()] if ollama_available() else []
    ollama = {"available": bool(models) or ollama_available(), "models": models, "roles": ["target", "grader"]}

    def _first(prefs: tuple[str, ...]) -> str | None:
        return next((m for p in prefs for m in models if m.startswith(p)), None)

    target_model = _first(("llama3.2:1b", "qwen2.5:1.5b", "gemma3:1b", "llama3.2", "qwen2.5"))
    prob_model = _first(("qwen2.5:7b", "qwen2.5:3b"))
    if cli_ok and cli["subscription"] == "ok":
        grader = f"claude-cli:{registry.resolve('judge_primary')}"
    elif prob_model:
        grader = f"ollama-prob:{prob_model}"
    else:
        grader = "host"
    return {
        "offline": offline(),
        "zero_spend": not metered_allowed("api"),
        "backends": {
            "claude_cli": cli,
            "ollama": ollama,
            "host": {"available": True, "roles": ["grader"],
                     "note": "the calling agent grades via MCP get_grading_tasks / submit_grades"},
            "api": {"available": False, "roles": [],
                    "note": f"metered; disabled unless {METERED_OPT_IN_ENV}=1 and chosen explicitly"},
        },
        "recommended": {
            "target": f"ollama:{target_model}" if target_model else None,
            "grader": grader,
        },
        "hints": _hints(cli, ollama, target_model),
    }


def _hints(cli: dict, ollama: dict, target_model: str | None) -> list[str]:
    out = []
    if not ollama["available"]:
        out.append("Install Ollama and run `ollama serve` to test open-weight models locally (free).")
    elif not target_model:
        out.append("Pull a small model to test: `ollama pull llama3.2:1b`.")
    if not cli["available"]:
        out.append("Install the Claude Code CLI to use Claude as a grader on your subscription.")
    elif "not logged in" in str(cli["subscription"]):
        out.append("The claude CLI is logged out — log in with your Claude subscription to use Claude "
                   "as a grader (Fusion never uses API-key auth).")
    elif str(cli["subscription"]).startswith("refused"):
        out.append("The claude CLI isn't on subscription auth — Fusion won't use it (nothing is billed).")
    return out
