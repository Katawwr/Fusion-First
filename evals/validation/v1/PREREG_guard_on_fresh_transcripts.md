# Pre-registration: the runtime guardrail on FRESH small-model attack transcripts

Registered 2026-09-27, while the transcripts it uses were still being generated and before the guard
was applied to any of them.

## Why

`guard_on_transcripts.json` (PREREG_guard_on_real_transcripts.md) measured the guardrail on the v1
evidence transcripts and found a bug (CamelCase read tools treated as consequential), fixed in a6fa0f5.
Re-measuring on the same transcripts would be a dev number. The compact-fix run generates, for every
model, the prompt as written on FRESH items (sample salt `fusion-evidence-compact-v1`, disjoint from
the v1 sample); no guard rule has been written or tuned against them.

## Design (fixed before data)

- **Transcripts:** arm `baseline` of the compact-fix run (salt `fusion-evidence-compact-v1`, excluding
  every v1 item), InjecAgent and Gandalf, models llama3.2:1b, qwen2.5:1.5b, gemma3:1b, qwen2.5:3b.
- **Rules under test:** `fusion/guardrail/` as of commit a6fa0f5, unchanged until this is scored.
- **Everything else** exactly as in PREREG_guard_on_real_transcripts.md: the same configurations, the
  same reading of tool calls (as the oracle reads them), the same outcomes (stopped / successful
  attacks; wrongly blocked / clean transcripts), 95% Wilson intervals, split by attack type.
- Scored once, when the compact-fix run is complete; reported whatever it shows.
