# Fusion First

**An offline test-and-prove engine for agentic AI safety.** Connect an agent (or paste a system
prompt); Fusion builds an OWASP-mapped attack suite, runs **baseline vs hardened**, and returns a
**Safety Report Card** where every number carries a confidence interval or an honesty badge — then
re-tests a suggested fix on your own model (so you see whether it helps: on the small open-weight
models we measured it rarely cut attacks and made them refuse more safe requests — see the
[Trust Report](TRUST_REPORT.md)) and gives you a runtime guardrail that holds even when the model
slips.

Covers the OWASP LLM Top 10 (2025) + Agentic AI (2026) risks:
`direct_prompt_injection` (LLM01), `excessive_agency` (LLM06), `data_exfiltration` (LLM02),
`system_prompt_leakage` (LLM07).

## Install

```bash
pip install fusion-safety            # core (keyless): runs, harden, runtime guardrail, CLI
pip install "fusion-safety[mcp]"     # + MCP server (fusion-mcp) for AI coding agents
```

> The `fusion` command, the runtime guardrail, `harden`, and the `check_output` / `check_tool_call`
> protect tools work from a bare install. The attack-suite commands (`scan`, `ci`, `guard-bench`,
> `prove`) read the committed corpora (`datasets/`, `cassettes/`, `crosswalk/`, `evals/`); run those
> from a source checkout until the data ships bundled in the package.

How far to trust Fusion itself (judge accuracy against deterministic oracles, guard held-out
results, what isn't measured yet) is in [`TRUST_REPORT.md`](TRUST_REPORT.md), which is generated
from committed evidence.

## Use it without an API key

Fusion tests a **real model running your prompt**: a local open-weight model through Ollama (free),
or Claude through your `claude` CLI subscription. The judge is Claude Code itself (host-as-judge)
or a built-in keyless grader, and every report card shows the grader's accuracy **measured in that
run** on questions with known answers.

**1. Claude Code plugin** (recommended): see `plugins/fusion/README.md`.

```bash
claude plugin marketplace add /path/to/fusion && claude plugin install fusion@fusion-first
# then in Claude Code:  /fusion:audit prompts/support_bot.md ollama:llama3.2:1b
```

**2. Command line / CI**

```bash
fusion doctor                                                    # what can run here, keyless
fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader ollama-prob:qwen2.5:7b
fusion run start --prompt agent.txt --target ollama:llama3.2:1b  # grader=host: stops for grading
fusion run tasks > tasks.json;  fusion run submit --file answers.json
fusion run finalize --min-grade B                               # exit 1 below the bar
fusion run verify                                               # re-derive offline; exit 1 on drift
fusion harden --prompt agent.txt --write                        # apply the tested fix in place
fusion run logs --file logs.jsonl --check everything --grader ollama-prob:qwen2.5:7b  # grade EXISTING transcripts
fusion import-promptfoo results.json                            # Wilson CIs + paired McNemar on promptfoo results
fusion guard-bench                              # benchmark the runtime guard (in-house corpus: 100% recall / 0% over-block)
```

**MCP** (any client): `fusion-mcp` (stdio) exposes `fusion_doctor`, `start_run`, `run_status`,
`get_grading_tasks`, `submit_grades`, `finalize_run`, `verify_run`, plus the one-shot
`audit_agent` / `scan_prompt` / `harden_prompt` / `check_output` / `check_tool_call` tools.

```json
{ "mcpServers": { "fusion": { "command": "fusion-mcp" } } }
```

**3. Runtime guardrail in your agent code** (and `plugins/fusion-guard` for Claude Code itself)

```python
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import GuardConfig
from fusion.guardrail.client import GuardedModelClient

guard = Guardrail(GuardConfig(allowlisted_domains=["your-co.com"], secret_values=["sk-..."], system_prompt=SYSTEM_PROMPT))
client = GuardedModelClient(your_model_client, guard)   # responses + tool calls now gated
```

See `integrations/README.md` for the full agentic/CI workflow. Offline runs report `DEMONSTRATION`
numbers from a deterministic stand-in judge on canned responses. Use `--live` for real numbers: it
runs through a local Ollama model and/or the `claude` CLI subscription — no API key. Metered API keys
are never used unless you pass `--backend api` AND set `FUSION_ALLOW_API_SPEND=1`.

## Develop

```bash
python -m pytest -q                 # full offline suite
python -m ruff check fusion tests scripts
```

The pure core lives in `fusion/` (never imports `modal`); the Modal/FastAPI wrappers live in `app/`.
See `CLAUDE.md` for the project guide and `SCHEMA.md` for the data model.
