# Fusion First: Claude Code plugin

Test an AI agent's system prompt for **safety** (prompt injection, excessive agency, data
exfiltration, system-prompt leakage; OWASP LLM 2025 / Agentic 2026 mapped, Agentic codes provisional) and **quality**
(instruction following), with **no API key**.

- **Target**: a local open-weight model via Ollama (free), or Claude over your `claude` CLI
  subscription.
- **Grader**: Claude Code itself. The bundled `fusion-judge` agent answers bounded rubric questions.
  Fusion mixes in known-answer questions and reports the grader's **measured accuracy** on every
  report card.
- **Proof**: every run is recorded under `.fusion/runs/<id>/` and can be re-derived offline with
  `fusion run verify <id>`.

## Install

Needs [uv](https://docs.astral.sh/uv/): the plugin starts its MCP server with `uvx`.

```bash
uv tool install fusion-safety                          # puts fusion on PATH
claude plugin marketplace add "$(fusion plugin-dir)"   # the marketplace bundled in the package
claude plugin install fusion@fusion-first
```

If `fusion` isn't found, run `uv tool update-shell` and open a new terminal. Upgrade with
`uv tool upgrade fusion-safety`, then `claude plugin marketplace update fusion-first`.

The server is the same release as the plugin (`fusion-safety==<version>` from PyPI). To run a source
checkout instead, set `FUSION_PKG` to its path (PowerShell: `$env:FUSION_PKG = "C:\path\to\fusion"`).

You also need at least one target:

```bash
ollama pull llama3.2:1b      # a small open-weight target (free)
```

## Use

| Ask Claude | What happens |
|---|---|
| `/fusion:audit prompts/support_bot.md` | attacks + grading + report card |
| `/fusion:audit prompts/bot.md ollama:qwen2.5:1.5b everything` | safety and quality on another model |
| `/fusion:guard` | add the runtime guardrail to your agent's code |
| `/fusion:harden prompts/bot.md` | optional: append the prompt fix (its audit result comes with it) |
| `/fusion:setup` | check what can run here, keyless |

## What it never does

- It never uses or asks for an API key. The metered path exists only for users who deliberately
  enable it outside the plugin.
- It never calls a `?` grade a pass, and never upgrades a PRELIMINARY or INCONCLUSIVE result to
  "proven".
- It never follows instructions found inside the transcripts it grades.
