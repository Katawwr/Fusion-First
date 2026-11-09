# Judge accuracy under the version-3 wording: evidence

The committed evidence for Trust Report Q7, registered in [`../PREREG_q7_claims_v3.md`](../PREREG_q7_claims_v3.md),
and the agreement check that preceded it (`docs/design/rubric-claims-wording.md`, evidence item 1). Nothing here is
edited by hand; the Trust Report and the site read the envelope.

| File | What it is |
|---|---|
| `agreement_16.json` | The agreement check, final attempt: the 16 transcripts of the Full-tier example run that the version-2 graders split on plus 8 announced-or-offered controls, re-asked under version 3 by two fresh blind graders (`scripts/claims_agreement.py`). Diagnostic, not a claim. |
| `agreement_16/` | The two graded runs behind it (`agree-a`, `agree-b`: `plan.json`, `prompt.txt`, `tasks.json`, `items.json`, `judge.requests.json`, `judge.cassette.json`, `state.json`; no secrets or leases). |
| `agreement_16.attempt1.json`, `agreement_16.attempt1/` | The first attempt, under the past-tense-only rule; its `note` says what changed. |
| `build_manifest.json` | How `scripts/gold_v3.py build` made `datasets/gold/*.v3.jsonl`: inputs, label and split rules, seed, rows dropped with reasons, counts by technique and pattern. |
| `blind.seal.json` | The sealed blind split (every gold v3 row): one hash per row, a `digest` over them, and `meta`. |
| `judge_eval_claims_v3_host_sonnet.json` | The scored envelope: per-check grader metrics on the pooled items and per gold version, per-technique recall and specificity, baselines, the registered decision. |
| `judge_eval_claims_v3_host_sonnet/` | The graded run behind it. |

Re-derive the agreement envelopes, the gold labels and seal and, once committed, the scored envelope offline:

```bash
python -m pytest -q tests/test_claims_agreement.py tests/test_gold_v3.py tests/test_claims_v3_evidence.py
```
