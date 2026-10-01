"""The runtime guard inside a live agent loop: AgentDojo (ethz-spylab/agentdojo, MIT; owner approved 2026-10-01).

Each episode runs one AgentDojo user task (optionally with one injection task, attack `important_instructions`)
on a local Ollama model with tools. Every tool call passes through the guard before it runs; a blocked call
does not run and the agent sees an error. AgentDojo's own checks score the episode: utility (the user's task
done) and security (True = the injection task succeeded).

Arms: `none` (no guard), `v2` (the user's request + untrusted_context once a tool result exists, as step 2 and
the snippet), `v3` (v2 + every tool result so far as `untrusted_text`). Guard: require_authorization=True plus
the per-suite deployment settings in SUITE_CONFIG.

Model responses are cached by the full request (model, messages, tools, options): arms share the cache until
their trajectories diverge, so a guarded episode costs only the turns after its first block. With temperature 0
and a fixed seed, a cached turn is the turn the model would produce.

Runs in its own venv (agentdojo pins its own dependencies):

    py=$LOCALAPPDATA/fusion-agentdojo-venv/Scripts/python
    $py scripts/agentdojo_guard.py plan  --split dev
    $py scripts/agentdojo_guard.py run   --split dev --model qwen2.5:7b --arms none,v2,v3 [--limit N]
    $py scripts/agentdojo_guard.py report --split dev --model qwen2.5:7b

Local Ollama only; no spend. One Ollama job at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
import urllib.request
from collections.abc import Sequence

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, load_system_message  # noqa: E402
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement  # noqa: E402
from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage  # noqa: E402
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor  # noqa: E402
from agentdojo.attacks.attack_registry import load_attack  # noqa: E402
from agentdojo.functions_runtime import Env, FunctionCall, FunctionsRuntime  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402
from agentdojo.types import (  # noqa: E402
    ChatAssistantMessage,
    ChatMessage,
    ChatToolResultMessage,
    get_text_content_as_str,
    text_content_block_from_string,
)

from fusion_first.guardrail.guard import Guardrail  # noqa: E402
from fusion_first.guardrail.policy import GuardConfig  # noqa: E402

BENCHMARK = "v1.2.2"
SUITES = ("workspace", "travel", "banking", "slack")
ATTACK = "important_instructions"
SPLIT_SALT = "fusion-agentdojo-split-v1"
DEV_FRACTION = 1 / 3
OLLAMA = "http://127.0.0.1:11434"
OPTIONS = {"temperature": 0, "seed": 7, "num_ctx": 16384, "num_predict": 1024}
MAX_ITERS = 15
DIR = ROOT / "evals/validation/v1/agentdojo"
CACHE_DIR = ROOT / ".fusion/agentdojo-cache"

# What a deployer would configure: the user's own organisation and addresses (from each suite's environment).
SUITE_CONFIG = {
    "workspace": {"allowlisted_domains": ["bluesparrowtech.com"], "user_identities": ["emma.johnson@bluesparrowtech.com"]},
    "travel": {"allowlisted_domains": [], "user_identities": []},
    "banking": {"allowlisted_domains": [], "user_identities": []},
    "slack": {"allowlisted_domains": [], "user_identities": []},
}
ARMS = ("none", "v2", "v3")


# ----------------------------------------------------------------------------------------------- splits
def _bucket(key: str) -> float:
    return int(hashlib.sha256(f"{SPLIT_SALT}:{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def split_of(suite: str, task_id: str) -> str:
    """dev or heldout, for a user task or an injection task (each split on its own)."""
    return "dev" if _bucket(f"{suite}:{task_id}") < DEV_FRACTION else "heldout"


def episodes(split: str) -> list[tuple[str, str, str | None]]:
    """(suite, user task, injection task or None): every user task of the split alone, then every pair of a
    user task and an injection task both in the split."""
    out = []
    for name in SUITES:
        suite = get_suite(BENCHMARK, name)
        users = sorted((t for t in suite.user_tasks if split_of(name, t) == split), key=_task_num)
        injs = sorted((t for t in suite.injection_tasks if split_of(name, t) == split), key=_task_num)
        out += [(name, u, None) for u in users]
        out += [(name, u, i) for u in users for i in injs]
    return out


def _task_num(task_id: str) -> int:
    return int(task_id.rsplit("_", 1)[1])


# ------------------------------------------------------------------------------------------------ model
def _jsonable(x):
    return json.loads(json.dumps(x, default=str, sort_keys=True))


def to_ollama(messages: Sequence[ChatMessage]) -> list[dict]:
    out = []
    for m in messages:
        role = m["role"]
        if role in ("system", "user"):
            out.append({"role": role, "content": get_text_content_as_str(m["content"])})
        elif role == "assistant":
            msg = {"role": "assistant", "content": get_text_content_as_str(m["content"] or [])}
            if m.get("tool_calls"):
                msg["tool_calls"] = [{"function": {"name": c.function, "arguments": dict(c.args)}}
                                     for c in m["tool_calls"]]
            out.append(msg)
        elif role == "tool":
            text = get_text_content_as_str(m["content"])
            if m.get("error"):
                text = f"{text}\nError: {m['error']}".strip()
            out.append({"role": "tool", "content": text, "tool_name": m["tool_call"].function})
    return out


def tool_schemas(runtime: FunctionsRuntime) -> list[dict]:
    return [{"type": "function", "function": {"name": f.name, "description": f.description,
                                              "parameters": f.parameters.model_json_schema()}}
            for f in runtime.functions.values()]


class Cache:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.data: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.data[r["key"]] = r["message"]
        self.hits = self.misses = 0

    def get(self, key: str) -> dict | None:
        return self.data.get(key)

    def put(self, key: str, message: dict) -> None:
        self.data[key] = message
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"key": key, "message": message}) + "\n")


def ollama_chat(model: str, messages: list[dict], tools: list[dict]) -> dict:
    body = json.dumps({"model": model, "messages": messages, "tools": tools, "options": OPTIONS,
                       "stream": False}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())["message"]


class OllamaLLM(BasePipelineElement):
    """A tool-calling chat model served by local Ollama, through the cache."""

    def __init__(self, model: str, cache: Cache, chat=ollama_chat):
        self.model, self.cache, self.chat = model, cache, chat
        self.calls = 0

    def query(self, query: str, runtime: FunctionsRuntime, env: Env,
              messages: Sequence[ChatMessage], extra_args: dict):
        msgs, tools = to_ollama(messages), tool_schemas(runtime)
        key = hashlib.sha256(json.dumps(_jsonable({"model": self.model, "messages": msgs, "tools": tools,
                                                   "options": OPTIONS}), sort_keys=True).encode()).hexdigest()
        reply = self.cache.get(key)
        if reply is None:
            self.cache.misses += 1
            reply = self.chat(self.model, msgs, tools)
            reply = {"content": reply.get("content") or "", "tool_calls": reply.get("tool_calls") or []}
            self.cache.put(key, reply)
        else:
            self.cache.hits += 1
        self.calls += 1
        calls = []
        for i, c in enumerate(reply["tool_calls"]):
            fn = c.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(FunctionCall(function=fn.get("name", ""), args=args if isinstance(args, dict) else {},
                                      id=f"call_{len(messages)}_{i}"))
        out = ChatAssistantMessage(role="assistant", content=[text_content_block_from_string(reply["content"])],
                                   tool_calls=calls or None)
        return query, runtime, env, [*messages, out], extra_args


# ------------------------------------------------------------------------------------------------ guard
class GuardedToolsExecutor(BasePipelineElement):
    """ToolsExecutor with the guard in front: a blocked call does not run and returns an error."""

    def __init__(self, arm: str, config: GuardConfig):
        if arm not in ARMS:
            raise ValueError(arm)
        self.arm, self.inner = arm, ToolsExecutor()
        self.guard = Guardrail(config) if arm != "none" else None
        self.decisions: list[dict] = []

    def query(self, query: str, runtime: FunctionsRuntime, env: Env,
              messages: Sequence[ChatMessage], extra_args: dict):
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1].get("tool_calls"):
            return query, runtime, env, messages, extra_args
        last = messages[-1]
        results = [get_text_content_as_str(m["content"]) for m in messages if m["role"] == "tool"]
        text = "\n\n".join(results) if self.arm == "v3" else ""
        allowed, blocked = [], {}
        for call in last["tool_calls"]:
            if self.guard is None:
                allowed.append(call)
                continue
            out = self.guard.guard_tool_call(call.function, dict(call.args), user_request=query,
                                             untrusted_context=bool(results), untrusted_text=text)
            self.decisions.append({"tool": call.function, "args": _jsonable(dict(call.args)), "blocked": out.blocked,
                                   "events": [e.detail for e in out.events]})
            if out.blocked:
                blocked[call.id] = ChatToolResultMessage(
                    role="tool", content=[text_content_block_from_string("")], tool_call_id=call.id, tool_call=call,
                    error="Blocked by the runtime guard: " + "; ".join(e.detail for e in out.events))
            else:
                allowed.append(call)
        ran = {}
        if allowed:
            trimmed = [*messages[:-1], {**last, "tool_calls": allowed}]
            _, _, env, after, _ = self.inner.query(query, runtime, env, trimmed, extra_args)
            ran = {m["tool_call_id"]: m for m in after[len(trimmed):]}
        ordered = [blocked.get(c.id) or ran[c.id] for c in last["tool_calls"]]
        return query, runtime, env, [*messages, *ordered], extra_args


class Recorder(BasePipelineElement):
    def __init__(self):
        self.messages: list = []

    def query(self, query, runtime, env, messages, extra_args):
        self.messages = list(messages)
        return query, runtime, env, messages, extra_args


def guard_config(suite: str) -> GuardConfig:
    return GuardConfig(require_authorization=True, **SUITE_CONFIG[suite])


def run_episode(suite_name: str, user_id: str, inj_id: str | None, arm: str, model: str, cache: Cache,
                chat=ollama_chat, attack: str = ATTACK) -> dict:
    suite = get_suite(BENCHMARK, suite_name)
    llm = OllamaLLM(model, cache, chat)
    executor = GuardedToolsExecutor(arm, guard_config(suite_name))
    recorder = Recorder()
    pipeline = AgentPipeline([SystemMessage(load_system_message(None)), InitQuery(), llm,
                              ToolsExecutionLoop([executor, llm], max_iters=MAX_ITERS), recorder])
    pipeline.name = "local"  # the attack addresses the model by this name ("Local model")
    user = suite.get_user_task_by_id(user_id)
    inj = suite.get_injection_task_by_id(inj_id) if inj_id else None
    injections = load_attack(attack, suite, pipeline).attack(user, inj) if inj else {}
    t0 = time.time()
    utility, security = suite.run_task_with_pipeline(pipeline, user, inj, injections)
    return {"suite": suite_name, "user_task": user_id, "injection_task": inj_id, "arm": arm, "model": model,
            "attack": attack if inj else None, "utility": bool(utility), "security": bool(security) if inj else None,
            "guard": executor.decisions, "llm_turns": llm.calls, "seconds": round(time.time() - t0, 1),
            "messages": _jsonable([to_ollama([m])[0] if m["role"] != "system" else {"role": "system"}
                                   for m in recorder.messages])}


# ------------------------------------------------------------------------------------------------- CLI
def _out(split: str, model: str, attack: str = ATTACK) -> pathlib.Path:
    suffix = "" if attack == ATTACK else f"__{attack}"
    return DIR / split / f"{model.replace(':', '-')}{suffix}.jsonl"


def _done(path: pathlib.Path) -> set[tuple]:
    if not path.exists():
        return set()
    return {(r["suite"], r["user_task"], r["injection_task"], r["arm"])
            for r in map(json.loads, filter(str.strip, path.read_text(encoding="utf-8").splitlines()))}


def cmd_run(a) -> int:
    path = _out(a.split, a.model, a.attack)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache = Cache(CACHE_DIR / f"{a.model.replace(':', '-')}.jsonl")
    done = _done(path)
    arms = [x for x in a.arms.split(",") if x]
    eps = episodes(a.split)
    if a.attacked_only:
        eps = [e for e in eps if e[2] is not None]
    if a.benign_only:
        eps = [e for e in eps if e[2] is None]
    eps = eps[:: a.stride][: a.limit or None]
    todo = [(s, u, i, arm) for s, u, i in eps for arm in arms if (s, u, i, arm) not in done]
    for n, (s, u, i, arm) in enumerate(todo, 1):
        try:
            r = run_episode(s, u, i, arm, a.model, cache, attack=a.attack)
        except ValueError as e:  # e.g. tool_knowledge needs placeholder args the injection task lacks
            print(f"{n}/{len(todo)} {s} {u} {i} {arm}: skipped ({e})", flush=True)
            continue
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(r) + "\n")
        blocked = sum(d["blocked"] for d in r["guard"])
        print(f"{n}/{len(todo)} {s} {u} {i or '-'} {arm}: utility={r['utility']} security={r['security']} "
              f"blocked={blocked} turns={r['llm_turns']} {r['seconds']}s (cache {cache.hits}/{cache.hits + cache.misses})",
              flush=True)
    return 0


def summarize(rows: list[dict]) -> dict:
    out = {}
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        benign = [r for r in rs if r["injection_task"] is None]
        attacked = [r for r in rs if r["injection_task"] is not None]
        out[arm] = {"benign": len(benign), "benign_utility": sum(r["utility"] for r in benign),
                    "attacked": len(attacked), "attack_success": sum(r["security"] for r in attacked),
                    "attacked_utility": sum(r["utility"] for r in attacked)}
    return out


def cmd_report(a) -> int:
    path = _out(a.split, a.model, a.attack)
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    print(json.dumps(summarize(rows), indent=1))
    return 0


def cmd_plan(a) -> int:
    eps = episodes(a.split)
    print(f"{a.split}: {sum(i is None for _, _, i in eps)} benign episodes, {sum(i is not None for _, _, i in eps)} "
          f"attacked episodes per arm and model")
    for name in SUITES:
        suite = get_suite(BENCHMARK, name)
        print(f"  {name}: user {[u for u in suite.user_tasks if split_of(name, u) == a.split]}")
        print(f"  {name}: injection {[i for i in suite.injection_tasks if split_of(name, i) == a.split]}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="agentdojo_guard")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "report"):
        sp = sub.add_parser(name)
        sp.add_argument("--split", choices=("dev", "heldout"), required=True)
        if name != "plan":
            sp.add_argument("--model", required=True)
            sp.add_argument("--attack", default=ATTACK, help="an AgentDojo attack name")
        if name == "run":
            sp.add_argument("--arms", default="none,v2,v3")
            sp.add_argument("--limit", type=int, default=0, help="first N episodes only (smoke)")
            sp.add_argument("--attacked-only", action="store_true")
            sp.add_argument("--benign-only", action="store_true")
            sp.add_argument("--stride", type=int, default=1, help="every Nth episode (a spread-out sample)")
    a = p.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
