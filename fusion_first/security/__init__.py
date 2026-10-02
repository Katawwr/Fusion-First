"""Security primitives (pure, offline-testable).

- redaction.py: scrub secrets/PII before they reach logs, responses, or shared report cards.
- budget.py: a ModelClient wrapper enforcing model allowlist + per-run call/token ceilings
  (a circuit breaker against runaway agent cost — OWASP LLM10 Unbounded Consumption).
"""
