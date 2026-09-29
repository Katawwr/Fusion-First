# Fusion First

**Measure and guard AI agents.** Fusion attacks an agent's system prompt with an OWASP-mapped suite,
grades safety and quality with a cross-family judge whose accuracy is measured in the same run, and
ships a runtime guardrail that blocks leaked secrets and tool calls the user's request does not cover
(measured results below). Every number carries a confidence interval or an honesty badge. The
prompt fix is optional and re-tested on your model (paired before/after, McNemar, honesty badge): on
the small open-weight models measured it rarely cut attacks and raised refusals of safe requests; see
the [Trust Report](https://fusion-first-testing.com/trust).

Checks (OWASP LLM Top 10 2025 / Agentic 2026): `direct_prompt_injection` (LLM01),
`excessive_agency` (LLM06), `data_exfiltration` (LLM02), `system_prompt_leakage` (LLM07).

## Install

```bash
pip install fusion-safety            # core: runs, runtime guardrail, CLI, prompt fix
pip install "fusion-safety[mcp]"     # + MCP server (fusion-mcp)
pip install "fusion-safety[serve]"   # + local web app (fusion serve)
```

The wheel bundles the corpora (`datasets/`, `cassettes/`, `crosswalk/`, `evals/`), the web app and
the Claude Code plugin marketplace (`fusion plugin-dir` prints its path).

## Use

Any model or workflow can be the target:

| Target | Runs | Cost |
|---|---|---|
| `ollama:<model>` | a local model; any Hugging Face GGUF as `ollama:hf.co/<user>/<repo>` | free |
| `openai-compat:<url>#<model>` | your own server: vLLM, TGI, LM Studio, llama.cpp | free if local |
| `claude-cli:<model>` | Claude via the `claude` CLI | subscription |
| `openai:` `hf:` `anthropic:` `openrouter:` `together:` `groq:` `fireworks:` `mistral-api:` `deepseek:` + `<model>` | a hosted API with your key (`OPENAI_API_KEY`, `HF_TOKEN`, ...) | metered; needs `FUSION_ALLOW_API_SPEND=1` |
| `cmd:<command>` | any workflow: a program that reads a JSON request on stdin and prints the reply (template: `integrations/examples/fusion_adapter.py`) | yours |
| `python:<name>` | a Python function, via `fusion.targets.FunctionModelClient` | yours |

Grader: `host` (the calling agent), `claude-cli`, or any chat target above. Each run measures its
grader on known-answer questions and withholds the grade ('?') if it falls short.

**1. Claude Code plugin** (recommended): see `plugins/fusion/README.md`.

```bash
uv tool install fusion-safety        # puts fusion on PATH; the plugin starts its server with uvx
claude plugin marketplace add "$(fusion plugin-dir)" && claude plugin install fusion@fusion-first
# in Claude Code:  /fusion:audit prompts/support_bot.md ollama:llama3.2:1b
```

**2. Command line / CI**

```bash
fusion doctor                                                    # available backends
fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader claude-cli
fusion run start --prompt agent.txt --target ollama:llama3.2:1b  # grader=host: pauses for grading
fusion run start --prompt agent.txt --target openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct --grader claude-cli  # vLLM / LM Studio / llama.cpp
fusion run start --prompt agent.txt --target hf:meta-llama/Llama-3.1-8B-Instruct --grader openai:gpt-4o  # hosted, your keys
fusion run start --prompt agent.txt --target "cmd:python fusion_adapter.py" --grader claude-cli  # any workflow
fusion run tasks > tasks.json;  fusion run submit --file answers.json
fusion run finalize --min-grade B                               # exit 1 below the bar
fusion run verify                                               # re-derive offline; exit 1 on drift
fusion harden --prompt agent.txt --write                        # optional: append the prompt fix
fusion run logs --file logs.jsonl --check everything --grader claude-cli  # grade existing transcripts
fusion import-promptfoo results.json                            # Wilson CIs + paired McNemar on promptfoo results
fusion guard-bench                              # runtime guard benchmark (in-house corpus: 100% recall / 0% over-block)
```

No local grader is recommended: `ollama-prob:qwen2.5:7b` scored below the policy floor in its
pre-registered test (Trust Report).

**MCP**: `fusion-mcp` (stdio) exposes `fusion_doctor`, `start_run`, `run_status`,
`get_grading_tasks`, `submit_grades`, `finalize_run`, `verify_run`, the one-shot `audit_agent` /
`scan_prompt`, the runtime guard's `guardrail_snippet` / `check_output` / `check_tool_call`, and the
optional `harden_prompt`.

```json
{ "mcpServers": { "fusion": { "command": "fusion-mcp" } } }
```

**3. Runtime guardrail** (in your agent code; `plugins/fusion-guard` for Claude Code)

On fresh successful attacks against qwen2.5:7b and llama3.1:8b (rules 0c560b5, scored once,
pre-registered), the guardrail stopped 89% of real attacks while wrongly blocking 1% of clean transcripts:
every password leak and direct-harm hijack, 69% of data-stealing hijacks. Llama Guard 3 8B, configured,
stopped 52% of the same attacks. The wrapper checks replies; each tool call is checked against the
user's own request before it runs. Every live scan also replays the guard over its own replies
(in-sample): the Guard step, the HTML report and `fusion run finalize` show what it would have stopped,
and count separately the attacks answered in prose, where there is no tool call to check.

```python
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import GuardConfig
from fusion.guardrail.client import GuardedModelClient

guard = Guardrail(GuardConfig(allowlisted_domains=["your-co.com"], secret_values=["sk-..."],
                              system_prompt=SYSTEM_PROMPT, require_authorization=True))  # the measured config
client = GuardedModelClient(your_model_client, guard)   # replies: secrets redacted, prompt dumps blocked
outcome = guard.guard_tool_call(tool_name, tool_args, user_request=user_message, untrusted_context=True)
if outcome.blocked: ...                                  # don't run it
```

**4. Local web app**

```bash
pip install "fusion-safety[serve]"
fusion serve                        # http://127.0.0.1:8765; --demo-only disables live models
```

Binds 127.0.0.1, accepts only `127.0.0.1`/`localhost` Host headers, and requires a per-launch token on
every request that runs anything, so other websites can't drive your local models or `claude`
subscription.

Offline runs report `DEMONSTRATION` numbers (deterministic stand-in judge, canned responses); `--live`
runs through Ollama and/or the `claude` CLI. Metered API keys are used only with `--backend api` and
`FUSION_ALLOW_API_SPEND=1`. Full CI workflow: `integrations/README.md`.

## Develop

```bash
python -m pytest -q                 # offline suite
python -m ruff check fusion tests scripts
```

`fusion/` is the pure core (never imports `modal`); Modal/FastAPI wrappers live in `app/`. See
`CLAUDE.md` (project guide) and `SCHEMA.md` (data model).
