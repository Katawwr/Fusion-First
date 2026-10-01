---
name: guard
description: Add Fusion First's runtime guardrail to an AI agent's code (redacts secrets/PII, blocks system-prompt dumps and tool calls the user's request does not cover), or check a single model output or tool call. Use when the user wants runtime protection for an agent they are building.
argument-hint: "[checks]"
---

# Runtime guardrail

The guard is the measured protection on small open-weight models; the prompt fix rarely cut attacks
there (Trust Report).

- **Add it to code:** call `guardrail_snippet(checks)` and adapt it to the user's agent loop. The
  `GuardedModelClient` wrapper checks replies only. Tool calls need `guard.guard_tool_call(name, args,
  user_request=..., untrusted_context=True, untrusted_text=<tool results so far>)` before each one
  runs, as in the snippet. Put the config (allowlisted domains, secret values) where the project keeps
  settings. Never hard-code real secrets. Set the allowlist: without one, step 2's destination rule
  blocked 12 of 20 legitimate actions (every send to the user's own address; Trust Report).
- **Check one output:** `check_output(text, secret_values=[...], system_prompt=...)` returns
  whether it is safe to send and the redacted text.
- **Check one tool call:** `check_tool_call(name, arguments, user_request, allowlisted_domains=[...])`
  returns allow / block with the reason. `user_request` is the user's own words, never tool output.
  It defaults to `require_authorization=True`: every call that is not a read must match the request,
  even without `untrusted_context`. `untrusted_context=True` (tool results or documents are in the
  conversation) also blocks unrequested reads of private data. `untrusted_text` (the text of those
  results) adds the step-3 rule: a read that text asks for, and the user did not, is blocked when the
  text also asks to send data to a non-allowlisted outside address; reads the user asked for pass.
  Consequential calls to a non-allowlisted host are blocked; an allowlist entry matches the exact host
  or a subdomain, and the user's own addresses are not exempt unless allowlisted.

Pick the autonomy level with the user. Supervised holds consequential actions for a human.
Autonomous runs unattended but still redacts leaks.
