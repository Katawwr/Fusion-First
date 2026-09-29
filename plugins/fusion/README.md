# Fusion First — Claude Code plugin

Test an AI agent's system prompt for **safety** (prompt injection, excessive agency, data
exfiltration, system-prompt leakage; OWASP LLM 2025 / Agentic mapped) and **quality**
(instruction following), with **no API key**.

- **Target**: a local open-weight model via Ollama (free), or Claude over your `claude` CLI
  subscription.
- **Grader**: Claude Code itself. The bundled `fusion-judge` agent answers bounded rubric questions.
  Fusion mixes in known-answer questions and reports the grader's **measured accuracy** on every
  report card.
- **Proof**: every run is recorded under `.fusion/runs/<id>/` and can be re-derived offline with
  `fusion run verify <id>`.

## Install (local checkout)

```bash
# 1. make the package reachable by uvx (until it is published)
export FUSION_PKG=/path/to/fusion          # PowerShell: $env:FUSION_PKG = "C:\path\to\fusion"
# 2. add this repo as a marketplace and install the plugin
claude plugin marketplace add /path/to/fusion
claude plugin install fusion@fusion-first
```

For a quick trial without installing: `claude --plugin-dir /path/to/fusion/plugins/fusion`.

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
