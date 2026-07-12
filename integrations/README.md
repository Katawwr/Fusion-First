# Fusion First in your agentic / CI workflow

Fusion's find → fix → protect loop is available three ways beyond the web app, so it can live
*inside* how you already build and ship AI agents. All of it is offline and deterministic (a
`DEMONSTRATION` grade with no API key; supply a provider key for live numbers).

| You want to… | Use |
|---|---|
| Let an **AI coding agent** grade/fix/guard a prompt while it writes code | **MCP server** |
| **Fail a build** when an agent prompt is unsafe | **CI gate** (`fusion ci`) |
| **Protect a running agent** (block leaks & unsafe tool calls) | **runtime guardrail** SDK |

---

## 1. MCP server — Fusion inside Claude Code / Cursor / Windsurf

An MCP server exposes Fusion's tools to any MCP-capable coding agent. Mid-build, the agent can grade
the system prompt it just wrote, apply the fix, and gate its own outputs and tool calls.

```bash
pip install "fusion-safety[mcp]"
python -m fusion.integrations.mcp_server   # stdio transport
```

Register it with your editor (`examples/mcp-config.json`):

```json
{
  "mcpServers": {
    "fusion-safety": { "command": "python", "args": ["-m", "fusion.integrations.mcp_server"] }
  }
}
```

Tools the agent gets:

- `list_checks()` — the safety checks + OWASP mapping
- `scan_prompt(system_prompt, checks?, tier?)` — **find** issues: grades + what got through
- `harden_prompt(system_prompt, checks?)` — **fix**: the hardened prompt + guard block
- `guardrail_snippet(checks?)` — **protect**: the runtime-guardrail code to drop in
- `check_output(text, secret_values?, system_prompt?)` — **protect (runtime)**: gate a response
- `check_tool_call(name, arguments, user_request?, …)` — **protect (runtime)**: gate a tool call

Example agent loop: *"I wrote a support-bot prompt → `scan_prompt` says F on prompt injection →
`harden_prompt` → paste the hardened prompt back → `guardrail_snippet` → wire the runtime guard."*

The same functions are a plain Python library too:

```python
from fusion.integrations import agent_tools
report = await agent_tools.scan_prompt(MY_SYSTEM_PROMPT)
fixed = agent_tools.harden_prompt(MY_SYSTEM_PROMPT)["hardened_prompt"]
```

---

## 2. CI gate — stop an unsafe prompt from shipping

`fusion ci` scans a system-prompt file and exits non-zero if the prompt **as written** scores below
`--min-grade` on any check. Drop it into any pipeline (`examples/github-action.yml`,
`examples/pre-commit-config.yaml`).

```bash
python scripts/fusion_cli.py ci --prompt prompts/support_bot.txt --min-grade B
# exit 0 = pass, exit 1 = a check is below the bar (run `fusion harden … --write` and re-scan)
```

`--json` emits machine-readable results. Offline this reports DEMONSTRATION numbers; add a provider
key for live grading of your actual prompt.

---

## 3. Runtime guardrail — protect the running agent

The prompt fix asks the model to behave; the guardrail makes sure it does — deterministic, model-free,
and independently benchmarked (100% recall / 0% over-block on the committed adversarial corpus, see
`python scripts/fusion_cli.py guard-bench`).

```python
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import GuardConfig
from fusion.guardrail.client import GuardedModelClient

guard = Guardrail(GuardConfig(
    allowlisted_domains=["your-company.com"],
    secret_values=["sk-...your-key..."],
    system_prompt=SYSTEM_PROMPT,
    require_authorization=True,
))
client = GuardedModelClient(your_model_client, guard)   # every response + tool call is now gated
```

## Where else this fits

- **Prompt registries / eval suites**: gate every prompt change in review.
- **Agent frameworks** (LangChain/LlamaIndex/custom): wrap the model client with the guardrail.
- **Data pipelines that call LLMs**: `check_output` before persisting or forwarding a response.
- **Support/ops copilots**: `check_tool_call` before executing a refund/delete/transfer.
