# Pre-registration: Fusion's rubric judge vs a plain single-question judge (B3)

Registered 2026-09-27, before any B3 answer was collected.

## Why

Fusion's core technical claim is that its rubric-decomposed judge (per-criterion questions, quoted
evidence, grading rules) is more accurate than simply asking an LLM whether a transcript is unsafe.
Q1 (`judge_eval_host_sonnet.json`) measured the rubric judge against deterministic oracles, but only
next to rule-based baselines. It has never been compared with a plain LLM judge on the same items.
If the plain judge does as well, the claim is unsupported and must not be made.

## Design (fixed before data)

- **Items:** exactly the 120 transcripts scored in `judge_eval_host_sonnet.json` (llama3.2:1b,
  InjecAgent graded as `direct_prompt_injection`, Gandalf graded as `system_prompt_leakage`, both
  arms, 60 per check). Labels: the same pre-registered deterministic oracles.
- **Rubric judge:** the committed answers in `judge_eval_host_sonnet/` (not re-run).
- **B3 judge:** Claude Sonnet as a Claude Code subagent (the same model and harness as the rubric
  run), batches of 10. Each subagent sees only `SingleQuestionJudge`'s request for each task: one
  yes/no question, the untrusted-content note and the transcript. It gets no rubric, no fusion-judge
  rules and never the labels. One pass, scored once.
- **Primary outcome:** pooled over both checks, the accuracy difference (rubric minus B3) on items
  both judges answered, with a paired bootstrap 95% interval, and a paired exact McNemar test on
  correctness (two-sided, alpha 0.05). Per-check results are reported as secondary.
- **Decision rule:** "the rubric judge beats a plain LLM judge" may be claimed only if the pooled
  difference has a 95% lower bound above 0 AND McNemar p < 0.05. Otherwise the Trust Report states
  that the rubric judge is not shown to beat a plain LLM judge, and no copy may claim it.
- **Missing answers:** unanswered or unparseable B3 answers are counted and excluded from the primary
  analysis; a sensitivity analysis counts them as wrong.

## What will not be done

- The B3 question wording (`CHECK_DESCRIPTIONS` and `SingleQuestionJudge` in
  `fusion/validate/baselines.py`) will not change after seeing answers.
- B3 will not be re-run to obtain a different answer. Any revision needs a new registration and
  new items.
