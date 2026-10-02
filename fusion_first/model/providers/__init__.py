"""Model providers.

Keyless: `ollama`, `claude_cli` (subscription auth), `openai_compat`, `command`.
Metered, opt-in only: `anthropic`, `openai` (key plus FUSION_ALLOW_API_SPEND=1).
Offline: `heuristic` and `demo_detectors`, the deterministic stand-in judge for demo cassettes.
"""
