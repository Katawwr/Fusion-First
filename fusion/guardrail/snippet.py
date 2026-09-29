"""Render the copy-paste runtime-guardrail code snippet (pure core; no HTTP/Modal).

The snippet is the configuration the published guardrail result measured (`require_authorization=True`):
replies pass through `GuardedModelClient` (secrets and PII redacted, a system-prompt dump blocked), and
every tool call is checked with `guard_tool_call` against the user's own request, with
`untrusted_context=True` once tool results or documents are in the conversation. The wrapper checks
replies only; tool calls need the explicit call.
"""

from __future__ import annotations

import textwrap

from fusion.engine.fixes import get_remedy
from fusion.judge.rubric import checks_of_kind


def guardrail_snippet(checks: list[str]) -> str:
    # The guard covers the safety checks; quality is graded, not guarded. None asked: all it covers.
    safety = checks_of_kind("safety")
    covered = list(dict.fromkeys(c for c in checks if c in safety)) or safety
    # Lines stay within ~80 columns so the snippet reads without scrolling in the web app's code box.
    covers = "\n#         ".join(textwrap.wrap(", ".join(get_remedy(c).title for c in covered), 68))
    return f'''# Fusion First runtime guardrail
# Covers: {covers}
# pip install fusion-safety
from fusion.guardrail.client import GuardedModelClient
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import GuardConfig

guard = Guardrail(GuardConfig(
    allowlisted_domains=["your-company.com"],  # other hosts are external
    secret_values=["sk-...your-key..."],       # must never appear in a reply
    system_prompt=SYSTEM_PROMPT,               # a reply dumping it is blocked
    require_authorization=True,  # calls must match the request (measured)
))

# Replies: secrets and PII are redacted; a system-prompt dump is blocked.
client = GuardedModelClient(your_model_client, guard)

# Tool calls: check each one before it runs. user_request is the user's own
# message, never tool output. untrusted_context=True once tool results or
# documents are in the conversation (then unrequested reads of private data
# are blocked too).
outcome = guard.guard_tool_call(tool_name, tool_args,
                                user_request=user_message,
                                untrusted_context=True)
if outcome.blocked:
    ...  # don't run it; show outcome.events or ask the user to confirm
'''
