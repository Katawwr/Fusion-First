---
description: Scaffold a new safety check — rubric, gold rows, crosswalk tag, and a calibration baseline.
---

Add a new safety check named in $ARGUMENTS (e.g. `indirect_prompt_injection`, `excessive_agency`).

Follow the existing `direct_prompt_injection` pattern, safety-first:

1. Add a `Rubric` in `fusion_first/judge/rubric.py` with 2-4 **binary, evidence-bearing** criteria and an
   `OwaspTag`. Register it in `REGISTRY`.
2. Add the check to `crosswalk/owasp_crosswalk.v2025.yaml` under `checks:` with valid LLM/ASI codes.
3. Author `datasets/gold/<check>.v1.jsonl` (balanced issue/non-issue, dev + blind splits, include
   deliberate traps) and `datasets/probes/<check>.v1.jsonl` (paired baseline/hardened).
4. Extend the offline stand-in in `fusion_first/model/providers/heuristic.py` if the new criteria need
   detection logic (offline demo only).
5. `python scripts/fusion_cli.py record --check <check>` then
   `python scripts/fusion_cli.py eval --check <check> --update-baseline`.
6. Add a test mirroring `tests/test_proof_pipeline.py` for the new check.
7. Run `python -m pytest -q` and `python -m ruff check`. All green before finishing.

Keep the scope to **safety** (injection, secret leakage, unsafe actions, excessive agency, data
exfiltration), not subjective quality — the user configures their own quality indicators.
