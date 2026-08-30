# Fusion First in your agentic / CI workflow

Fusion is a **proof-grade evaluation engine for AI agents — safety AND quality**. Its find → fix →
protect loop lives *inside* how you already build and ship agents. Every number carries a confidence
interval or an honesty badge, measured against ground truth (no vibes-based metrics).

**Best fit: open-weight / less-robust models.** Frontier models (Claude, GPT-4-class) resist most
safety attacks — verified, Claude Haiku 0% — but open-weight models (Llama, Mistral, Qwen, …) don't:
verified, llama3.2:1b fails 62% of injection and 67% of exfiltration attacks. Run your open-weight
agent **locally and free** via Ollama, judged by Claude (genuine cross-family independence). Quality
(instruction-following/correctness) matters on every model, including Claude.

| You want to… | Use |
|---|---|
| **Audit an agent** end-to-end (safety + quality, one call) | **MCP `audit_agent`** |
| **Test an open-weight agent** locally & free | `--backend ollama` (Ollama target, Claude judge) |
| Let an **AI coding agent** grade/fix/guard a prompt mid-build | **MCP server** |
| **Fail a build** when an agent prompt is unsafe | **CI gate** (`fusion ci`) |
| Run the **self-improving loop** (sufficiency / accuracy / quality) | `fusion measure` |
| **Protect a running agent** (block leaks & unsafe tool calls) | **runtime guardrail** SDK |

No API key needed: real calls go through the local Ollama server and/or the `claude` CLI
subscription. Offline, `scan_prompt` reports a labelled `DEMONSTRATION` grade.

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

- `audit_agent(system_prompt, autonomy?, backend?, target_model?)` — **start here**: FIND + FIX +
  PROTECT across **safety AND quality** in one call → plain-language verdict, overall grade, hardened
  prompt, runtime-guardrail snippet, and the runtime config for your `autonomy` (supervised = HITL
  gates; autonomous = unattended + redact).
- `grade_quality(system_prompt, backend?, target_model?)` — grade an agent's correctness /
  instruction-following on normal test inputs (A–F + the failing inputs).
- `list_checks()` — the safety + quality checks (grouped by `kind`)
- `scan_prompt(system_prompt, checks?, tier?, live?, backend?, target_model?)` — **find** safety issues
- `harden_prompt(system_prompt, checks?)` — **fix**: the hardened prompt + guard block
- `guardrail_snippet(checks?)` — **protect**: the runtime-guardrail code to drop in
- `check_output(text, secret_values?, system_prompt?)` — **protect (runtime)**: gate a response
- `check_tool_call(name, arguments, user_request?, …)` — **protect (runtime)**: gate a tool call

Audit an **open-weight** agent locally (free, no key), judged by Claude:

```python
from fusion.integrations import agent_tools
report = await agent_tools.audit_agent(MY_PROMPT, backend="ollama", target_model="llama3.2:1b")
# report["safety"] (attacks that landed) + report["quality"] (grade + failing inputs) + hardened_prompt
```

Example agent loop: *"I wrote a support-bot prompt → `audit_agent` says F on prompt injection and D on
instruction-following → paste back the hardened prompt → wire the runtime guard."*

The same functions are a plain Python library too:

```python
from fusion.integrations import agent_tools
report = await agent_tools.scan_prompt(MY_SYSTEM_PROMPT)
fixed = agent_tools.harden_prompt(MY_SYSTEM_PROMPT)["hardened_prompt"]
```

---

## 1b. Test an open-weight agent + the self-improving loop

Frontier models are hardened; open-weight models are where safety attacks actually land. Test one
locally, free, judged by Claude (cross-family):

```bash
# 1) run a local open-weight model
ollama serve && ollama pull llama3.2:1b

# 2) safety: do the attacks land? (sufficiency)
fusion measure --backend ollama --target-model llama3.2:1b --stages sufficiency
#   direct_prompt_injection: 62% landed … data_exfiltration: 67% landed   (vs Claude Haiku 0%)

# 3) quality: does the agent follow instructions? (grade its outputs)
fusion measure --backend ollama --target-model llama3.2:1b --stages quality --prompt agent.txt
#   instruction_following: quality grade D — 3/10 responses had a defect

# 4) accuracy: how good is the judge itself, vs oracle labels? (Bar A)
fusion measure --stages accuracy --check instruction_following
#   instruction_following  F1=1.00 kappa=1.00 …
```

`fusion measure` is the self-improving loop: sufficiency (are attacks strong enough?), quality (grade
the agent), accuracy (is the judge calibrated?). It records every model call to a cassette, so re-runs
are free. Needs a live backend (Ollama and/or the `claude` CLI); it is opt-in, never in CI.

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
