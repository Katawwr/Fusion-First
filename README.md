# Fusion First

**Evaluation engine for AI agents: safety and quality, with measured error bars.** Fusion attacks an
agent's system prompt with an OWASP-mapped suite, grades the transcripts with a cross-family judge
whose accuracy is measured in the same run, re-tests a prompt fix on your model (paired before/after,
McNemar, honesty badge), and ships a runtime guardrail. Every number carries a confidence interval or
an honesty badge. On the small open-weight models measured, the prompt fix rarely cut attacks and
raised refusals of safe requests; see the [Trust Report](TRUST_REPORT.md).

Checks (OWASP LLM Top 10 2025 / Agentic 2026): `direct_prompt_injection` (LLM01),
`excessive_agency` (LLM06), `data_exfiltration` (LLM02), `system_prompt_leakage` (LLM07).

## Install

```bash
pip install fusion-safety            # core: runs, harden, runtime guardrail, CLI
pip install "fusion-safety[mcp]"     # + MCP server (fusion-mcp)
pip install "fusion-safety[serve]"   # + local web app (fusion serve)
```

The wheel bundles the corpora (`datasets/`, `cassettes/`, `crosswalk/`, `evals/`) and the web app.

## Use (no API key)

Target: a local open-weight model via Ollama, an OpenAI-compatible server, or Claude via the `claude`
CLI subscription. Grader: Claude, either the calling agent (`host`) or the `claude` CLI. Each run
measures its grader on known-answer questions and withholds the grade ('?') if it falls short.

**1. Claude Code plugin** (recommended): see `plugins/fusion/README.md`.

```bash
claude plugin marketplace add /path/to/fusion && claude plugin install fusion@fusion-first
# in Claude Code:  /fusion:audit prompts/support_bot.md ollama:llama3.2:1b
```

**2. Command line / CI**

```bash
fusion doctor                                                    # available backends
fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader claude-cli
fusion run start --prompt agent.txt --target ollama:llama3.2:1b  # grader=host: pauses for grading
fusion run start --prompt agent.txt --target openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct --grader claude-cli  # vLLM / LM Studio / llama.cpp
fusion run tasks > tasks.json;  fusion run submit --file answers.json
fusion run finalize --min-grade B                               # exit 1 below the bar
fusion run verify                                               # re-derive offline; exit 1 on drift
fusion harden --prompt agent.txt --write                        # apply the fix in place
fusion run logs --file logs.jsonl --check everything --grader claude-cli  # grade existing transcripts
fusion import-promptfoo results.json                            # Wilson CIs + paired McNemar on promptfoo results
fusion guard-bench                              # runtime guard benchmark (in-house corpus: 100% recall / 0% over-block)
```

No local grader is recommended: `ollama-prob:qwen2.5:7b` scored below the policy floor in its
pre-registered test (Trust Report).

**MCP**: `fusion-mcp` (stdio) exposes `fusion_doctor`, `start_run`, `run_status`,
`get_grading_tasks`, `submit_grades`, `finalize_run`, `verify_run`, and the one-shot
`audit_agent` / `scan_prompt` / `harden_prompt` / `check_output` / `check_tool_call` tools.

```json
{ "mcpServers": { "fusion": { "command": "fusion-mcp" } } }
```

**3. Runtime guardrail** (in your agent code; `plugins/fusion-guard` for Claude Code)

On fresh successful attacks against four small open-weight models (current rules, scored once,
pre-registered), the guardrail stopped 71% of real attacks while wrongly blocking 1% of clean transcripts:
every password leak, under half of the tool hijacks.

```python
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import GuardConfig
from fusion.guardrail.client import GuardedModelClient

guard = Guardrail(GuardConfig(allowlisted_domains=["your-co.com"], secret_values=["sk-..."], system_prompt=SYSTEM_PROMPT))
client = GuardedModelClient(your_model_client, guard)   # responses and tool calls gated
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
