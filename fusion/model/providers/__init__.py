"""Model providers. `anthropic`/`openai` are live adapters (need keys, marked live in tests).
`heuristic` is a deterministic offline stand-in used to record demo cassettes so the whole
proof loop runs without network or keys — the swap point between 'demo' and 'real' numbers.
"""
