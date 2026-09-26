---
name: guard
description: Add Fusion First's runtime guardrail to an AI agent's code (blocks leaked secrets/PII, system-prompt reproduction, unauthorized or exfiltrating tool calls), or check a single model output or tool call. Use when the user wants runtime protection for an agent they are building.
argument-hint: "[checks]"
---

# Runtime guardrail

Prompt fixes reduce issues. The runtime guard catches what still slips through.

- **Add it to code:** call `guardrail_snippet(checks)` and adapt the snippet to the user's model
  client (it wraps the client, so every response and tool call passes through the guard). Put the
  config (allowlisted domains, secret values, whether consequential actions need authorization)
  where the project keeps settings. Never hard-code real secrets.
- **Check one output:** `check_output(text, secret_values=[...], system_prompt=...)` returns
  whether it is safe to send and the redacted text.
- **Check one tool call:** `check_tool_call(name, arguments, user_request, allowlisted_domains=[...])`
  returns allow / block with the reason.

Pick the autonomy level with the user. Supervised holds consequential actions for a human.
Autonomous runs unattended but still redacts leaks.
