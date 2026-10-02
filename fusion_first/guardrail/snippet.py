"""Render the copy-paste runtime-guardrail snippet: the configuration the published result measured."""

from __future__ import annotations

import textwrap

from fusion_first.engine.fixes import get_remedy
from fusion_first.judge.rubric import checks_of_kind


def guardrail_snippet(checks: list[str]) -> str:
    # Quality is graded, not guarded; with no safety check asked, cover them all.
    safety = checks_of_kind("safety")
    covered = list(dict.fromkeys(c for c in checks if c in safety)) or safety
    # ~80 columns so the web app's code box needs no scrolling.
    covers = "\n#         ".join(textwrap.wrap(", ".join(get_remedy(c).title for c in covered), 68))
    return f'''# Fusion First runtime guardrail
# Covers: {covers}
# pip install fusion-safety
from fusion_first.guardrail.client import GuardedModelClient
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import GuardConfig

guard = Guardrail(GuardConfig(
    allowlisted_domains=["your-company.com"],  # other hosts are external
    secret_values=["sk-...your-key..."],       # must never appear in a reply
    system_prompt=SYSTEM_PROMPT,               # a reply dumping it is blocked
    require_authorization=True,  # calls must match the request (measured)
))

# Replies: secrets and PII are redacted; a system-prompt dump is blocked.
client = GuardedModelClient(your_model_client, guard)

# Tool calls: check each one before it runs. user_request is the user's own
# message, never tool output. tool_results is the text of the tool results
# and documents in the conversation so far: a read they ask for alongside a
# send to an outside address is blocked, as are unrequested private reads.
outcome = guard.guard_tool_call(tool_name, tool_args,
                                user_request=user_message,
                                untrusted_context=True,
                                untrusted_text=tool_results)
if outcome.blocked:
    ...  # don't run it; show outcome.events or ask the user to confirm
'''
