---
name: setup
description: Check and set up what Fusion First needs to test agents without an API key (Ollama models, the claude CLI subscription). Use when Fusion reports no available target or the user asks how to get started.
---

# Fusion setup (keyless)

1. Call `fusion_doctor` and summarise what it found: Ollama models, claude CLI subscription
   status, and the recommended target and grader.
2. Suggest only what is missing:
   - **Local targets (free):** install Ollama from ollama.com, then `ollama pull llama3.2:1b`.
     Small open-weight models are where these attacks actually land.
   - **Local grader (optional, free):** `ollama pull qwen2.5:7b`, then use `ollama-prob:qwen2.5:7b`.
   - **Claude as target or grader:** the `claude` CLI logged in with a Claude subscription. Fusion
     refuses API-key auth, so nothing is billed per call. Usage counts toward the subscription quota.
3. Never ask for, or set, an API key. Fusion's metered path is off unless the user deliberately
   enables it themselves.
4. If the MCP server itself failed to start, the package isn't installed where `uvx` can find it.
   Set `FUSION_PKG` to a local checkout path (e.g. `FUSION_PKG=/path/to/fusion`) and restart
   Claude Code.
