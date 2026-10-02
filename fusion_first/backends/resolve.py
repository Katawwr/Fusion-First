"""Turn a target/grader spec string into a client, and report what is available (`doctor`).

  target  ollama:<model>        a local open-weight model (free)            e.g. ollama:llama3.2:1b
          claude-cli:<model>    a Claude model over the `claude` CLI subscription (no API key)
          openai-compat:<url>#<model>
                                YOUR model server (vLLM, LM Studio, llama.cpp, Ollama /v1...), e.g.
                                openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct. Local and
                                private-network servers are free; a public endpoint may be a metered
                                API, so it needs FUSION_ALLOW_API_SPEND=1
          openai:<model> hf:<model> openrouter:<model> together:<model> groq:<model>
          fireworks:<model> mistral-api:<model> deepseek:<model>
                                a hosted provider (fusion_first.backends.presets), with the user's own key
                                (OPENAI_API_KEY, HF_TOKEN, ...). METERED: needs FUSION_ALLOW_API_SPEND=1
          anthropic:<model>     the Anthropic API with ANTHROPIC_API_KEY. METERED, same opt-in
          cmd:<command line>    ANY workflow: a program reading one JSON request on stdin and printing the
                                reply (fusion_first.model.providers.command). CLI / Python API only by default
          python:<name>         an in-process Python function (fusion_first.targets.FunctionModelClient),
                                passed to fusion_first.runs.service.drive(target_client=...)
          <model>               bare id: an allowlisted Claude id → claude-cli, anything else → ollama
                                (Hugging Face GGUF models too: ollama:hf.co/<user>/<repo>)

  grader  host                  the calling agent grades (MCP get_grading_tasks / submit_grades)
          claude-cli[:<model>]  Claude over the CLI subscription (default: the judge_primary role)
          ollama-prob:<model>   the local probability judge (token log-probabilities)
          ollama:<model>        a local model answering the JSON rubric (weakest; measured in-run)
          <any chat target>     openai:, hf:, anthropic:, openai-compat:, cmd: ... answering the JSON
                                rubric. Every run measures its grader and withholds the grade below
                                the policy floor, so any grader is safe to try.

ZERO SPEND: nothing here ever selects a metered provider on its own; hosted providers need the
explicit opt-in AND the user's own key. The claude CLI provider refuses unless `claude auth status`
reports subscription auth, and strips paid-auth env vars from the child.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fusion_first.integrations.live import METERED_OPT_IN_ENV, metered_allowed
from fusion_first.model.registry import ModelRegistry

CHAT_GRADER_BACKENDS = ("openai_compat", "anthropic", "command")  # target specs that can also grade
OPAQUE_BACKENDS = ("command", "python")  # Fusion can't tell which model these run

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
    backend: str  # ollama | claude_cli | openai_compat | anthropic | command | python | api
    model: str  # for command: the command line; for python: a name
    base_url: str | None = None  # openai_compat only
    key_env: str | None = None  # a provider preset's key variable
    provider: str | None = None  # a provider preset's name (openai, hf, ...)

    @property
    def label(self) -> str:
        if self.provider:
            return f"{self.provider}:{self.model}"
        if self.backend == "command":
            return f"cmd:{self.model}"
        if self.base_url:
            return f"{self.backend.replace('_', '-')}:{self.base_url}#{self.model}"
        return f"{self.backend.replace('_', '-')}:{self.model}"


@dataclass(frozen=True)
class GraderSpec:
    kind: str  # host | claude_cli | ollama_prob | ollama_json | target
    model: str | None = None  # for target: the target spec label (openai:gpt-4o, cmd:..., ...)

    @property
    def label(self) -> str:
        if self.kind == "target":
            return self.model or ""
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


def _parse_open(spec: str) -> TargetSpec | None:
    """Provider presets, anthropic:, cmd: and python:, or None for the other spec forms."""
    from fusion_first.backends.presets import ALIASES, PROVIDERS

    head, sep, rest = spec.partition(":")
    name = ALIASES.get(head.lower(), head.lower())
    if not sep or name not in (*PROVIDERS, "anthropic", "cmd", "command", "python"):
        return None
    value = rest.strip()
    if not value:
        example = "a command line" if name in ("cmd", "command") else "<model>"
        raise SpecError(f"target '{spec}' is missing {example}, e.g. {name}:{example}")
    if name in PROVIDERS:
        url, key_env = PROVIDERS[name]
        return TargetSpec("openai_compat", value, url, key_env=key_env, provider=name)
    if name in ("cmd", "command"):
        return TargetSpec("command", value)
    return TargetSpec(name, value)  # anthropic | python


def parse_target(spec: str, registry: ModelRegistry | None = None) -> TargetSpec:
    spec = (spec or "").strip()
    if not spec:
        raise SpecError("empty target spec (try ollama:llama3.2:1b)")
    open_spec = _parse_open(spec)
    if open_spec is not None:
        return open_spec
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
        try:
            t = parse_target(spec)
        except SpecError:
            t = None
        if t is not None and t.backend in CHAT_GRADER_BACKENDS and ":" in spec:
            return GraderSpec("target", t.label)
        raise SpecError(
            f"unknown grader '{spec}' (use host, claude-cli[:model], ollama-prob:<model>, ollama:<model>, or a "
            "chat target such as openai:<model>, hf:<model>, anthropic:<model>, openai-compat:<url>#<model>, "
            "cmd:<command>)"
        )
    if kind in ("ollama_prob", "ollama_json") and not model:
        raise SpecError(f"grader '{spec}' needs a model, e.g. ollama-prob:qwen2.5:7b")
    return GraderSpec(kind, model or None)


def _cli_preflight() -> None:
    """Fail fast, before any collect, if the claude CLI isn't on subscription auth (no model call)."""
    import shutil

    from fusion_first.model.providers.claude_cli import (
        assert_subscription_auth,
        claude_cli_available,
        refuse_shell_shim,
    )

    if not claude_cli_available():
        raise BackendUnavailable("the `claude` CLI isn't on PATH (or FUSION_OFFLINE=1 is set)")
    binary = os.environ.get("FUSION_CLAUDE_BIN") or shutil.which("claude") or "claude"
    refuse_shell_shim(binary)
    assert_subscription_auth(binary)


def _require_spend_opt_in(what: str) -> None:
    if not metered_allowed("api"):
        raise BackendUnavailable(f"{what} is a metered API (your money), so it is off by default: set "
                                 f"{METERED_OPT_IN_ENV}=1 to allow it")


def _require_key(env: str, provider: str) -> str:
    key = os.environ.get(env)
    if not key:
        raise BackendUnavailable(f"set {env} to your {provider} API key")
    return key


def build_target_client(spec: TargetSpec, *, max_calls: int = 400, timeout: float = 600.0,
                        allow_command: bool = True):
    """A budgeted client for the target. `allow_command=False` (the MCP server default) refuses cmd: targets."""
    from fusion_first.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=max_calls)
    if spec.backend == "ollama":
        from fusion_first.model.providers.ollama import OllamaModelClient, ollama_available

        if not ollama_available():
            raise BackendUnavailable("Ollama isn't answering at 127.0.0.1:11434: run `ollama serve`")
        return BudgetedModelClient(
            OllamaModelClient(model=spec.model, timeout=timeout), limits, enforce_allowlist=False
        )
    if spec.backend == "claude_cli":
        from fusion_first.model.providers.claude_cli import ClaudeCliModelClient

        registry = ModelRegistry()
        registry.require_allowed(spec.model)
        _cli_preflight()
        return BudgetedModelClient(ClaudeCliModelClient(registry=registry), limits)
    if spec.backend == "openai_compat":
        from fusion_first.model.providers.openai_compat import API_KEY_ENV, OpenAICompatModelClient

        if not _private_endpoint(spec.base_url or "") and not metered_allowed("api"):
            raise BackendUnavailable(
                f"{spec.base_url} is a public endpoint and may be a metered API, so it is off by default: "
                f"set {METERED_OPT_IN_ENV}=1 to allow it (local and private-network servers need nothing)")
        if spec.key_env:
            _require_key(spec.key_env, spec.provider or "provider")
        client = OpenAICompatModelClient(spec.base_url, spec.model, timeout=timeout,
                                         api_key_env=spec.key_env or API_KEY_ENV)
        return BudgetedModelClient(client, limits, enforce_allowlist=False)
    if spec.backend == "anthropic":
        from fusion_first.backends.presets import ANTHROPIC_KEY_ENV
        from fusion_first.model.providers.anthropic import AnthropicModelClient

        _require_spend_opt_in(f"anthropic:{spec.model}")
        key = _require_key(ANTHROPIC_KEY_ENV, "Anthropic")
        registry = ModelRegistry()
        registry.allowlist.setdefault(spec.model, "anthropic")  # the user named this model explicitly
        client = _PinnedModel(AnthropicModelClient(api_key=key, registry=registry, timeout=timeout), spec.model)
        return BudgetedModelClient(client, limits, enforce_allowlist=False)
    if spec.backend == "command":
        from fusion_first.model.providers.command import ALLOW_REMOTE_ENV, CommandModelClient

        if not allow_command:
            raise BackendUnavailable(f"cmd: targets run a program on this machine, so they are off here: set "
                                     f"{ALLOW_REMOTE_ENV}=1 to allow them (the CLI always allows them)")
        return BudgetedModelClient(CommandModelClient(spec.model, timeout=timeout), limits, enforce_allowlist=False)
    if spec.backend == "python":
        raise SpecError("python: targets run in-process: pass target_client=fusion_first.targets.FunctionModelClient(fn) "
                        "to fusion_first.runs.service.drive")
    if spec.backend == "api":
        raise BackendUnavailable(
            "api: is retired for runs because it is metered. Name the provider instead (anthropic:<model>, openai:<model>, "
            f"hf:<model>, ...), which spends your own key and needs {METERED_OPT_IN_ENV}=1")
    raise SpecError(f"unknown target backend '{spec.backend}'")


def build_grader_client(spec: GraderSpec, *, max_calls: int = 1000, timeout: float = 600.0,
                        allow_command: bool = True):
    """A judge client for a built-in grader (`host` has none: the calling agent grades)."""
    from fusion_first.security.budget import BudgetedModelClient, BudgetLimits

    limits = BudgetLimits(max_calls=max_calls)
    if spec.kind == "host":
        raise SpecError("the host grader has no built-in client: grade via get_grading_tasks/submit_grades")
    if spec.kind == "target":
        return build_target_client(parse_target(spec.model or ""), max_calls=max_calls, timeout=timeout,
                                   allow_command=allow_command)
    if spec.kind == "claude_cli":
        from fusion_first.model.providers.claude_cli import ClaudeCliModelClient

        registry = ModelRegistry()
        judge_id = spec.model or registry.resolve("judge_primary")
        registry.require_allowed(judge_id)
        _cli_preflight()
        return BudgetedModelClient(ClaudeCliModelClient(registry=registry, judge_model=judge_id), limits)
    from fusion_first.model.providers.ollama import OllamaModelClient, ollama_available

    if not ollama_available():
        raise BackendUnavailable("Ollama isn't answering at 127.0.0.1:11434: run `ollama serve`")
    ollama = BudgetedModelClient(
        OllamaModelClient(model=spec.model, timeout=timeout), limits, enforce_allowlist=False
    )
    if spec.kind == "ollama_prob":
        from fusion_first.judge.prob_judge import ProbabilityJudge, ProbJudgeClient

        return ProbJudgeClient(ProbabilityJudge(ollama, model_id=spec.model))
    return _PinnedModel(ollama, spec.model)


class _PinnedModel:
    """Send every judge request to one local model (Judge requests carry no model id)."""

    def __init__(self, inner, model: str):
        self.inner, self.model = inner, model

    async def complete(self, request):
        return await self.inner.complete(request.model_copy(update={"model_id": self.model}))


# ------------------------------------------------------------------------------------ doctor


def doctor(*, check_auth: bool = True, auth_runner=None) -> dict:
    """What can run here, keyless. `check_auth` runs `claude auth status` (local, no model call)."""
    from fusion_first.model.providers.claude_cli import (
        ClaudeCliUnavailable,
        assert_subscription_auth,
        claude_cli_available,
    )
    from fusion_first.model.providers.ollama import ollama_available, ollama_models
    from fusion_first.offline import offline

    registry = ModelRegistry()
    cli = {"available": claude_cli_available(), "subscription": "not checked", "roles": ["target", "grader"]}
    if cli["available"] and check_auth:
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
    # A local grader is recommended only when its pre-registered measurement met the policy floor.
    from fusion_first.validate.prereg import local_grader_status

    local_graders = [local_grader_status(m) for p in ("qwen2.5:7b", "qwen2.5:3b") for m in models if m.startswith(p)]
    qualified = next((s["model"] for s in local_graders if s["meets_floor"]), None)
    hints = _hints(cli, ollama, target_model)
    if cli_ok and cli["subscription"] == "ok":
        grader = f"claude-cli:{registry.resolve('judge_primary')}"
    elif qualified:
        grader = f"ollama-prob:{qualified}"
    else:
        grader = "host"
        hints += [_local_grader_hint(s) for s in local_graders]
    return {
        "offline": offline(),
        "zero_spend": not metered_allowed("api"),
        "backends": {
            "claude_cli": cli,
            "ollama": ollama,
            "host": {"available": True, "roles": ["grader"],
                     "note": "the calling agent grades via MCP get_grading_tasks / submit_grades"},
            "hosted": _hosted_backends(),
            "command": {"available": True, "roles": ["target", "grader"], "spec": "cmd:<command>",
                        "over_mcp": _remote_commands_allowed()},
        },
        "recommended": {
            "target": f"ollama:{target_model}" if target_model else None,
            "grader": grader,
        },
        "hints": hints,
    }


def _hosted_backends() -> dict:
    """Which hosted-provider keys are present (never their values) and whether spending is allowed."""
    from fusion_first.backends.presets import ANTHROPIC_KEY_ENV, PROVIDERS

    keys = {name: env for name, (_, env) in PROVIDERS.items()} | {"anthropic": ANTHROPIC_KEY_ENV}
    opt_in = metered_allowed("api")
    return {
        "available": opt_in,
        "roles": ["target", "grader"],
        "spend_opt_in": opt_in,
        "providers": {name: {"spec": f"{name}:<model>", "key_env": env, "key_set": bool(os.environ.get(env))}
                      for name, env in keys.items()},
        "note": f"metered (your key); off unless {METERED_OPT_IN_ENV}=1",
    }


def _remote_commands_allowed() -> bool:
    from fusion_first.model.providers.command import remote_commands_allowed

    return remote_commands_allowed()


def _local_grader_hint(status: dict) -> str:
    m = status["model"]
    why = ("as a grader it scored below the policy floor in its pre-registered test (Trust Report: https://fusion-first-testing.com/trust)"
           if status["measured"] else "its accuracy as a grader has not been measured")
    return (f"{m} is installed, but {why}, so it is not recommended by default. You can still choose it with "
            f"--grader ollama-prob:{m}; every run measures its grader and withholds the grade if it falls short.")


def _hints(cli: dict, ollama: dict, target_model: str | None) -> list[str]:
    out = []
    if not ollama["available"]:
        out.append("Install Ollama and run `ollama serve` to test open-weight models locally (free).")
    elif not target_model:
        out.append("Pull a small model to test: `ollama pull llama3.2:1b`.")
    if not cli["available"]:
        out.append("Install the Claude Code CLI to use Claude as a grader on your subscription.")
    elif "not logged in" in str(cli["subscription"]):
        out.append("The claude CLI is logged out: log in with your Claude subscription to use Claude "
                   "as a grader (Fusion never uses API-key auth).")
    elif str(cli["subscription"]).startswith("refused"):
        out.append("The claude CLI isn't on subscription auth: Fusion won't use it (nothing is billed).")
    return out
