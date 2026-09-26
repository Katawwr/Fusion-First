# Fusion First

**An offline test-and-prove engine for agentic AI safety.** Connect an agent (or paste a system
prompt); Fusion builds an OWASP-mapped attack suite, runs **baseline vs hardened**, and returns a
**Safety Report Card** where every number carries a confidence interval or an honesty badge — then
hands you a one-click fix and a runtime guardrail that holds even when the model slips.

Covers the OWASP LLM Top 10 (2025) + Agentic AI (2026) risks:
`direct_prompt_injection` (LLM01), `excessive_agency` (LLM06), `data_exfiltration` (LLM02),
`system_prompt_leakage` (LLM07).

## Install

```bash
pip install fusion-safety            # core: harden, runtime guardrail, agent tools, CLI
pip install "fusion-safety[mcp]"     # + MCP server for AI coding agents
```

> The `fusion` command, the runtime guardrail, `harden`, and the `check_output` / `check_tool_call`
> protect tools work from a bare install. The attack-suite commands (`scan`, `ci`, `guard-bench`,
> `prove`) read the committed corpora (`datasets/`, `cassettes/`, `crosswalk/`, `evals/`); run those
> from a source checkout until the data ships bundled in the package.

## Use it three ways

**1. Command line / CI gate**

```bash
fusion scan   --prompt system_prompt.txt        # grade it; see what got through
fusion harden --prompt system_prompt.txt --write  # apply the fix in place
fusion ci     --prompt system_prompt.txt --min-grade B --live   # exit 1 if unsafe (needs a live backend)
fusion guard-bench                              # benchmark the runtime guard (in-house corpus: 100% recall / 0% over-block)
```

**2. Inside an AI coding agent (MCP)** — point Claude Code / Cursor at the server and it can grade,
fix, and guard the prompt it just wrote:

```json
{ "mcpServers": { "fusion-safety": { "command": "python", "args": ["-m", "fusion.integrations.mcp_server"] } } }
```

**3. Runtime guardrail in your agent code**

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
