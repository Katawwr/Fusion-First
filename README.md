<p align="center">
  <img src="frontend/public/ff.svg" alt="FF" width="72" height="72">
</p>

<h1 align="center">Fusion First</h1>

<p align="center">
  <b>Measure and guard AI agents.</b> Attack your agent, grade it with a grader whose accuracy is checked in every
  run, and block unsafe tool calls with a runtime guardrail.
</p>

<p align="center">
  <a href="https://fusion-first-testing.com">Site</a> ·
  <a href="https://fusion-first-testing.com/trust">Evidence</a> ·
  <a href="docs/RUN_LOCALLY.md">Run locally</a> ·
  <a href="https://pypi.org/project/fusion-safety/">PyPI</a>
</p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-504d9a">
  <img alt="PyPI" src="https://img.shields.io/pypi/v/fusion-safety?color=504d9a">
  <img alt="MCP server" src="https://img.shields.io/badge/MCP-server-504d9a">
  <img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude%20Code-plugin-504d9a">
</p>

## Results

> **The runtime guardrail stopped 89% of real attacks while wrongly blocking 1% of clean transcripts.**
> Llama Guard 3 8B, configured, stopped 52% of the same attacks.
>
> Given the tool results as well, it stopped 100% of data-stealing hijacks.

Pre-registered and scored once, on fresh attacks against qwen2.5:7b and llama3.1:8b (InjecAgent and Gandalf).
The grader, Claude Sonnet, scored 80% accuracy on direct prompt injection and 92% on system prompt leakage
against deterministic oracles. Every number is generated from committed evidence and checked by a test;
details on the [evidence page](https://fusion-first-testing.com/trust).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/guard-tradeoff-dark.png">
  <img alt="Attacks stopped against clean transcripts wrongly blocked: Fusion vs Llama Guard 3" src="docs/img/guard-tradeoff-light.png" width="720">
</picture>

## Use

```bash
pip install "fusion-safety[serve,mcp]"
fusion doctor                                                    # what can run here
fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader claude-cli
fusion run finalize --min-grade B                               # report card; exit 1 below the bar
fusion serve                                                    # the web app on 127.0.0.1:8765
```

Any model or agent can be the target: `ollama:<model>`, `openai-compat:<url>#<model>`, `claude-cli:<model>`, a
hosted API with your own key (`openai:`, `anthropic:`, `hf:`, ...; needs `FUSION_ALLOW_API_SPEND=1`), or any
program via `cmd:<command>`.

**Runtime guardrail** in your agent loop:

```python
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import GuardConfig

guard = Guardrail(GuardConfig(allowlisted_domains=["your-co.com"], require_authorization=True))
outcome = guard.guard_tool_call(tool_name, tool_args, user_request=user_message,
                                untrusted_context=True, untrusted_text=tool_results)
if outcome.blocked: ...                                  # don't run it
```

**Claude Code**: `claude plugin marketplace add "$(fusion plugin-dir)" && claude plugin install fusion@fusion-first`.
**MCP**: `{ "mcpServers": { "fusion": { "command": "fusion-mcp" } } }` exposes the run engine and the guard's
`guardrail_snippet` / `check_tool_call` tools.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/overview-dark.png">
  <img alt="The Fusion First site: method and pre-registered results" src="docs/img/overview-light.png" width="720">
</picture>

## Built with

Python 3.11 · FastAPI · React 19 / Vite / Tailwind · MCP · Modal · Vercel · pytest, vitest, Playwright.
Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
