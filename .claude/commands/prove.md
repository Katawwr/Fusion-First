---
description: Generate a Fusion Safety Report Card for a check (Bar A judge accuracy + Bar B before/after), with honest CIs and badges.
---

Produce the Safety Report Card.

1. Run `python scripts/fusion_cli.py prove --check ${1:-direct_prompt_injection}`.
2. Summarize for a non-expert: the grade, the before/after safety improvement with its honesty
   badge, and the judge's measured accuracy (with confidence intervals).
3. If the card is a DEMONSTRATION (offline stand-in judge), say so plainly — it validates the
   methodology, not a real efficacy claim. Real numbers require recording cassettes against a live
   judge key.

Never present a demonstration card as a real safety guarantee.
