"""Runtime-guardrail snippet for the fix screen. The generator now lives in the pure core
(`fusion.guardrail.snippet`) so the API, the CLI, and the agent tools all share one source."""

from __future__ import annotations

from fusion.guardrail.snippet import guardrail_snippet

__all__ = ["guardrail_snippet"]
