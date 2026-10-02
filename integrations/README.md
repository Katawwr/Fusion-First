# Fusion First in your agentic / CI workflow

Fusion measures an agent's safety and quality and guards it at runtime, inside the tools you already
use. Every number carries a confidence interval or an honesty badge. Grader accuracy is checked
against deterministic oracles, which answer narrow questions (a tool was called, a string appeared).

**Best fit: open-weight models.** Run the agent locally and free via Ollama, graded by Claude (a
different model family). How exposed a frontier model is has not been measured here; `fusion run`
measures whatever target you give it. Quality (instruction following, correctness) matters on every
model.

| You want to… | Use |
|---|---|
| **Test an agent** (safety + quality, graded, offline re-derivable) | `fusion run start --target …` (main path), or MCP `start_run` |
| **One-shot audit** from an AI coding agent | MCP `audit_agent` |
| **Fail a build** when an agent prompt is unsafe | `fusion run verify` + `finalize --min-grade` on a committed run, or `fusion ci --live` |
| **Protect a running agent** | the runtime guardrail ([README](../README.md#run-it-locally), section 3) |

No API key needed: real calls go through the local Ollama server and/or the `claude` CLI
subscription (plan usage only; keep "extra usage" disabled on your account to guarantee zero spend).
Hosted presets (`openai:`, `hf:`, `anthropic:`, `openrouter:`, ...) and `openai-compat:` URLs on the
public internet are metered: each needs `FUSION_ALLOW_API_SPEND=1` plus your key, and Fusion never
selects one on its own. Offline, results are labelled `DEMONSTRATION`.

---

## 1. MCP server: Fusion inside Claude Code / Cursor / Windsurf

```bash
pip install "fusion-safety[mcp]"
fusion-mcp                          # stdio transport
```

Register it with your editor (`examples/mcp-config.json`):

```json
{ "mcpServers": { "fusion": { "command": "fusion-mcp" } } }
```

Tools (18):

- **Run engine** (main path): `fusion_doctor`, `start_run`, `resume_run`, `run_status`,
  `get_grading_tasks`, `submit_grades`, `finalize_run`, `verify_run`, `list_runs`,
  `grade_transcripts` (existing logs).
- **One-shot**: `audit_agent` (safety + quality, guard snippet, optional hardened prompt),
  `scan_prompt`, `grade_quality`, `list_checks`.
- **Runtime guard**: `guardrail_snippet(checks?)`, `check_output(text, secret_values?, system_prompt?)`,
  `check_tool_call(name, arguments, user_request?, …, untrusted_context?, untrusted_text?)`.
- **Optional fix**: `harden_prompt(system_prompt, checks?)` (re-test it on your model; see the [Trust Report](../TRUST_REPORT.md)).

`check_tool_call` defaults to `require_authorization=True`, so a call that is not a read must match
`user_request` even without `untrusted_context`. `untrusted_context=True` adds the private-read gate;
`untrusted_text` (the tool results so far) adds the step-3 rule. The rules are described once, with
their measured results, in the [README](../README.md#run-it-locally) (section 3).

The same functions are a plain Python library:

```python
from fusion_first.integrations import agent_tools
report = await agent_tools.audit_agent(MY_PROMPT, backend="ollama", target_model="llama3.2:1b")
# report["safety"] (attacks that landed) + report["quality"] (grade + failing inputs) + guardrail_snippet
```

---

## 2. Test an open-weight agent

Main path: the run engine, which records everything and can be re-derived offline.

```bash
ollama pull llama3.2:1b
fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader claude-cli
```

One-shot path (`--backend ollama`, no recorded run): `fusion measure` is the self-improving loop:
sufficiency (do the attacks land?), quality (grade the agent), accuracy (the judge vs oracle labels).
It needs a live backend and is opt-in, never in CI.

```bash
fusion measure --backend ollama --target-model llama3.2:1b --stages sufficiency
fusion measure --backend ollama --target-model llama3.2:1b --stages quality --prompt agent.txt
fusion measure --stages accuracy --check instruction_following
```

---

## 3. CI gate: stop an unsafe prompt from shipping

**Proof-carrying runs (no model in CI).** CI machines usually have no Ollama and no Claude login. Run
the evaluation on a developer machine, commit `.fusion/runs/<run_id>/`, and let CI re-derive it
offline (`examples/github-action.yml`):

```bash
fusion run verify $RUN_ID --prompt prompts/support_bot.txt   # the run tested THIS prompt, unmodified
fusion run finalize $RUN_ID --min-grade B                    # exit 1 below the bar; a withheld '?' fails
```

**One-shot gate** (`examples/pre-commit-config.yaml`), on a machine with a model:

```bash
fusion ci --prompt prompts/support_bot.txt --min-grade B --live
# exit 0 = pass, exit 1 = a check is below the bar (add the runtime guardrail; optionally `fusion harden … --write` and re-test)
```

`--live` grades your actual prompt through a local Ollama model or the `claude` CLI subscription.
Without `--live` or `--demo`, `fusion ci` refuses (exit 2): demonstration responses are canned and do
not depend on your prompt. `--demo` is an advisory demonstration run that always exits 0. `--json`
emits machine-readable results.

---

## Where else this fits

- **Prompt registries / eval suites**: gate every prompt change in review.
- **Agent frameworks** (LangChain/LlamaIndex/custom): wrap the model client and check each tool call
  with `guard_tool_call` before it runs.
- **Data pipelines that call LLMs**: `check_output` before persisting or forwarding a response.
- **Support/ops copilots**: `check_tool_call` before executing a refund/delete/transfer.
- **Any other workflow** as a target: `cmd:<command>` with `examples/fusion_adapter.py`.
