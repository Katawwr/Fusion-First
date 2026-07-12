"""Render the copy-paste runtime-guardrail code snippet (pure core; no HTTP/Modal).

The prompt fix (`apply_fix`) asks the model to behave; the runtime guardrail makes sure it does —
it blocks leaked secrets and unauthorized tool calls even when the model slips. Python today; the
appended prompt guard block works everywhere.
"""

from __future__ import annotations

from fusion.engine.fixes import get_remedy

_DEFAULT_CONSEQUENTIAL = sorted(
    {
        "send_email", "http_post", "delete_records", "transfer_funds",
        "approve_refund", "grant_access", "make_purchase",
    }
)


def guardrail_snippet(checks: list[str]) -> str:
    titles = ", ".join(get_remedy(c).title for c in checks)
    tools_repr = ", ".join(f'"{t}"' for t in _DEFAULT_CONSEQUENTIAL)
    return f'''# Fusion First runtime guardrail — the "bouncer" between your bot and the world.
# Covers: {titles}
# pip install fusion-safety
from fusion.guardrail.client import GuardedModelClient
from fusion.guardrail.guard import Guardrail
from fusion.guardrail.policy import GuardConfig

guard = Guardrail(GuardConfig(
    # Where sensitive data is allowed to go. Anything else is treated as external.
    allowlisted_domains=["your-company.com"],
    # Consequential tools the guard must see explicit authorization for.
    consequential_tools=[{tools_repr}],
    # Exact secret strings that must never appear in an output.
    secret_values=["sk-...your-key..."],
    # Your agent's own system prompt — used to detect verbatim leakage.
    system_prompt=SYSTEM_PROMPT,
))

# Wrap whatever model client you already use; every response is now guarded.
client = GuardedModelClient(your_model_client, guard)
'''
