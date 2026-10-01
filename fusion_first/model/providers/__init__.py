"""Model providers.

Keyless: `ollama` (local models), `claude_cli` (the `claude` CLI on subscription auth),
`openai_compat` (any OpenAI-compatible server), `command` (any program over stdin/stdout).
Metered, opt-in only: `anthropic`, `openai` (need a key and FUSION_ALLOW_API_SPEND=1; live tests).
Offline: `heuristic` + `demo_detectors` are a deterministic stand-in judge used to record demo
cassettes, so the whole proof loop runs without network or keys — the swap point between 'demo'
and 'real' numbers.
"""
