"""Attacks: the OWASP taxonomy and the attack builders.

- taxonomy.py: resolves and validates OWASP codes from the pinned crosswalk YAML (tests pin every
  rubric's tag to the crosswalk's entry for its check).
- templates.py: turns a user's system prompt into attack trajectories, seeded from the probe corpus.
- agentic.py: a text tool-call protocol so a text-only target's tool use is observable.
- adaptive.py: an LLM attacker scored by the real judge (development tooling, not shipped).
"""
