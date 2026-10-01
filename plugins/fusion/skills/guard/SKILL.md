---
name: guard
description: Add Fusion First's runtime guardrail to an AI agent's code (blocks leaked secrets/PII, system-prompt reproduction, unauthorized or exfiltrating tool calls), or check a single model output or tool call. Use when the user wants runtime protection for an agent they are building.
argument-hint: "[checks]"
---

# Runtime guardrail

The guard is the measured protection on small open-weight models; the prompt fix rarely cut attacks
there (Trust Report).

- **Add it to code:** call `guardrail_snippet(checks)` and adapt it to the user's agent loop. The
  `GuardedModelClient` wrapper checks replies only. Tool calls need `guard.guard_tool_call(name, args,
  user_request=..., untrusted_context=True, untrusted_text=<tool results so far>)` before each one runs, as in the snippet. Put the config
  (allowlisted domains, secret values) where the project keeps settings. Never hard-code real secrets.
- **Check one output:** `check_output(text, secret_values=[...], system_prompt=...)` returns
  whether it is safe to send and the redacted text.
- **Check one tool call:** `check_tool_call(name, arguments, user_request, allowlisted_domains=[...])`
  returns allow / block with the reason. `user_request` is the user's own words, never tool output.
  Pass `untrusted_context=True` once tool results or documents are in the conversation: every call
  that is not a read must then match the request, and unrequested reads of private data are blocked.
  Pass the text of those tool results as `untrusted_text`: a read it asks for alongside a send to an
  outside address is blocked too.

Pick the autonomy level with the user. Supervised holds consequential actions for a human.
Autonomous runs unattended but still redacts leaks.
