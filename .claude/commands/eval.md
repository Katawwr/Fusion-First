---
description: Run the Fusion accuracy eval gate for a check (default direct_prompt_injection) and report pass/fail vs baseline.
---

Run the offline accuracy gate and report the result.

1. Run `python -m pytest -m unit -q` and note pass/fail.
2. Run `python scripts/fusion_cli.py eval --check ${1:-direct_prompt_injection}`.
3. Report the `[eval:...]` line and whether it passed the user-configured policy and the
   regression baseline. If red, say which metric regressed and by how much.

Do not pass `--update-baseline` unless the user explicitly asks to re-seed the baseline.
