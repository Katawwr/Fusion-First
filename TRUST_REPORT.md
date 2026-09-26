# Fusion First — Trust Report

This report answers four questions about Fusion itself: **is it detecting accurately, does it error
often, does the fix work, and does it add value over simpler checks?** It is generated from committed
evidence files by `python -m fusion.validate.trust_report` — nothing here is typed by hand, and a test
fails if this file and its evidence disagree. Intervals are 95% Wilson (rates) unless noted. Evidence
from the offline stand-in judge (`demonstration: true`) is never used here.

## Q1 — Is the judge accurate?

Grader verdicts on **real open-weight model transcripts**, scored against **deterministic oracles** (no LLM in the ground truth): did the model call the attacker's tool (InjecAgent), did it leak the planted password (Gandalf). Baselines answer the same items.

| Evidence | Grader | Check | n | Accuracy | Recall | Specificity | F1 | κ | vs naive regex (F1) | vs tuned heuristic (F1) |
|---|---|---|---|---|---|---|---|---|---|---|
| `evals/validation/v1/judge_eval_host_sonnet.json` | Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules) | direct_prompt_injection | 60 | 80% (68%–88%) | 80% (55%–93%) | 80% (66%–89%) | 0.67 | 0.53 | 0.53 (McNemar p=0.503) | 0.10 (p=0.189) |
| `evals/validation/v1/judge_eval_host_sonnet.json` | Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules) | system_prompt_leakage | 60 | 92% (82%–96%) | 100% (76%–100%) | 90% (78%–95%) | 0.83 | 0.77 | 0.42 (McNemar p=0.180) | 0.00 (p=0.143) |

Disagreement audit (`evals/validation/v1/judge_eval_host_sonnet.json`): ambiguous (attacker tool called, but addressed to the legitimate user): 3; disagreements: 17; grader stricter than the oracle (flagged acknowledging a hidden rule): 4; oracle missed a real violation (grader right per the rubric): 10. Most injection disagreements are llama3.2:1b writing natural-language ACTION lines or committing in prose, which the tool-name oracle cannot see; the leakage ones are the grader applying the rubric strictly to refusals that acknowledge a secret exists. The oracles were pre-registered and are not changed after seeing the grader.

Every run also measures its own grader in-run (known-answer questions + an oracle cross-check on the run's clear-cut questions) and withholds the grade when the grader falls below the policy floor.

## Q3 — Does the fix work, and what does it cost?

NOT YET MEASURED — the oracle-labelled evidence run on local open-weight models has not been committed yet.

## Runtime guard for Claude Code (fusion-guard hook)

Tool calls written by independent agents **blind to the rules**; each set scored once.

| Set | benign n | Prompted (over-block) | attack n | Caught (recall) | Caught, .test hosts as public | Status |
|---|---|---|---|---|---|---|
| v1 | 80 | 6% (3%–14%) | 60 | 65% (52%–76%) | — | PRE-TUNING |
| v2 | 100 | 5% (2%–11%) | 70 | 33% (23%–44%) | 61% (50%–72%) | HELD OUT at rules_git_sha |

Pattern rules catch the common exfiltration / destruction / remote-code shapes and miss much of the long tail; treat the hook as defense in depth, not a sandbox.

## Known limits

- Oracle labels decide narrow questions (a tool was called, a password appeared). Where the judge's rubric is broader than the oracle, some 'disagreements' are real violations the oracle can't see — see each disagreement audit.
- Samples are small (tens of transcripts per cell); read the intervals, not the points.
- Known-answer questions come from a public gold set; the in-run oracle cross-check covers only clear-cut questions.
