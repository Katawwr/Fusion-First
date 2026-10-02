---
name: setup
description: Check and set up what Fusion First needs to test agents without an API key (Ollama models, the claude CLI subscription). Use when Fusion reports no available target or the user asks how to get started.
---

# Fusion setup (keyless)

1. Call `fusion_doctor` and summarise what it found: Ollama models, claude CLI subscription
   status, and the recommended target and grader.
2. Suggest only what is missing:
   - **Local targets (free):** install Ollama from ollama.com, then `ollama pull llama3.2:1b`.
     Fusion's measurements so far are on small open-weight models (Trust Report).
   - **Grader:** Claude grades: as the host (the fusion-judge agent) or through the claude CLI. Don't
     suggest a local grader: `ollama-prob:qwen2.5:7b` scored below the policy floor in its pre-registered
     test (Trust Report: https://fusion-first-testing.com/trust), and an unmeasured local model is no
     better evidence.
   - **Claude as target or grader:** the `claude` CLI logged in with a Claude subscription. Fusion
     refuses API-key auth, so nothing is billed per call. Usage counts toward the subscription quota.
3. Never ask for, or set, an API key. Fusion's metered path is off unless the user deliberately
   enables it themselves.
4. If the MCP server itself failed to start: it runs `uvx --from fusion-safety==<version>`, so `uv`
   must be installed and PyPI reachable. To run a local checkout instead, set `FUSION_PKG` to its
   path and restart Claude Code.
