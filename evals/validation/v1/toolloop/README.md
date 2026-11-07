# Judge accuracy on tool trajectories: evidence

The committed evidence for Trust Report Q6, registered in [`../PREREG_q1_toolloop.md`](../PREREG_q1_toolloop.md).
Nothing here is edited by hand; the Trust Report and the site read the envelope.

| File | What it is |
|---|---|
| `build_manifest.json` | How `scripts/gold_v2.py build` made `datasets/gold/*.v2.jsonl`: inputs, label and split rules, seed, rows dropped as undecidable. |
| `blind.seal.json` | The sealed blind split: one hash per blind row, a `digest` over them, and `meta` (build date, counts, gold file hashes). |
| `judge_eval_toolloop_host_sonnet.json` | The scored envelope: per-check grader metrics, per-technique recall, baselines, the registered decision. |
| `judge_eval_toolloop_host_sonnet/` | The graded run behind it: `plan.json`, `prompt.txt`, `items.json`, `tasks.json`, `state.json` (with the rejected submissions) and `judge.cassette.json` (the grader's answers). |

Provenance notes:

- `blind.seal.json` `meta.git_sha` (1f046ed) names the worktree commit the data was built at; that work was
  cherry-picked onto main as f384103. The row hashes and their digest bind the seal, not the meta: `verify_seal`
  recomputes each row's hash from the committed gold, and the envelope records the digest it was scored under.
- The run's `plan.json` says `"version": "v1"`. That is an artifact of `prepare` not passing the corpus version at
  the time (fixed since; new runs record `v2`). The questions were the gold v2 blind cases, which
  `tests/test_toolloop_evidence.py` re-derives from the committed gold.
- The registration (cc84cce) was amended at ae041c5, before any grading: the scorer refuses an incompletely graded
  run, and the decision fails closed when too many questions go unanswered.

Re-derive the envelope from the committed run, offline:

```bash
python -m pytest -q tests/test_toolloop_evidence.py
```
