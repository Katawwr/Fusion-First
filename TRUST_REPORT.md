# Fusion First — Trust Report

This report answers four questions about Fusion itself: **is it detecting accurately, does it error
often, does the fix work, and does it add value over simpler checks?** It is generated from committed
evidence files by `python -m fusion.validate.trust_report` — nothing here is typed by hand, and a test
fails if this file and its evidence disagree. Intervals are 95% Wilson (rates) unless noted. Evidence
from the offline stand-in judge (`demonstration: true`) is never used here.

## Q1 — Is the judge accurate?

Grader verdicts on **real open-weight model transcripts**, scored against **deterministic oracles** (no LLM in the ground truth): did the model call the attacker's tool (InjecAgent), did it leak the planted password (Gandalf). The two rule-based baselines answer the same items. Unanswered items are excluded from the rates and counted.

| Evidence | Grader | Check | n (unanswered) | Accuracy | Recall | Specificity | F1 | κ | Naive regex F1 | Tuned heuristic F1 |
|---|---|---|---|---|---|---|---|---|---|---|
| `evals/validation/v1/judge_eval_host_sonnet.json` | Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules) | direct_prompt_injection | 60 (0) | 80% (68%–88%) | 80% (55%–93%) | 80% (66%–89%) | 0.67 | 0.53 | 0.53 | 0.10 |
| `evals/validation/v1/judge_eval_host_sonnet.json` | Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules) | system_prompt_leakage | 60 (0) | 92% (82%–96%) | 100% (76%–100%) | 90% (78%–95%) | 0.83 | 0.77 | 0.42 | 0.00 |

Disagreement audit (`evals/validation/v1/judge_eval_host_sonnet.json`) — Every grader-vs-oracle disagreement was read by the maintainer model (Claude Opus) and classified. This is an LLM reading of the transcripts, NOT ground truth; the primary metrics above stay grader-vs-oracle. ambiguous (attacker tool called, but addressed to the legitimate user): 3; disagreements: 17; grader stricter than the oracle (flagged acknowledging a hidden rule): 4; oracle missed a real violation (grader right per the rubric): 10. Most injection disagreements are llama3.2:1b writing natural-language ACTION lines or committing in prose, which the tool-name oracle cannot see; the leakage ones are the grader applying the rubric strictly to refusals that acknowledge a secret exists. The oracles were pre-registered and are not changed after seeing the grader.

How to read this: the paired McNemar test asks whether the grader and a baseline get different ITEMS right (not whether their F1 differs). None of the 4 grader-vs-baseline comparisons is significant at 0.05 yet — the grader scores higher, but these samples can't rule out chance.
Each item appears twice (the prompt as written and with the fix), so the rows are not fully independent and the intervals are somewhat too narrow. The leakage oracle is itself a string match for the planted password; the baselines are generic and are not told the password.

Every run also measures its own grader in-run (known-answer questions + an oracle cross-check on the run's clear-cut questions) and withholds the grade when the grader falls below the policy floor.

## Q3 — Does the fix work, and what does it cost?

The prompt as written vs the same prompt with Fusion's fix applied, on real local models (llama3.2:1b), over held-out items from external benchmarks. Issue = oracle-confirmed attack success (InjecAgent: the attacker's tool was called; Gandalf: the planted password leaked) or an oracle-confirmed cost (XSTest: a SAFE request refused; IFEval: an instruction not followed). Lower is better in every row. Evidence: `evals/validation/v1/evidence_oracle.json`.

| Experiment | Model | Pairs | As written | With fix | Paired test | What it shows |
|---|---|---|---|---|---|---|
| injecagent | llama3.2:1b | 30 | 17% (7%–34%) | 33% (19%–51%) | McNemar p=0.125 | worse with the fix, not significant |
| gandalf | llama3.2:1b | 30 | 20% (10%–37%) | 20% (10%–37%) | McNemar p=1.000 | no change |
| xstest | llama3.2:1b | 30 | 10% (3%–26%) | 33% (19%–51%) | McNemar p=0.039 | **significantly worse with the fix** |
| ifeval | llama3.2:1b | 24 | 67% (47%–82%) | 62% (43%–79%) | McNemar p=1.000 | better with the fix, not proven (PRELIMINARY) |

Significant regressions: xstest on llama3.2:1b. Proven improvements: none yet.
This is why every Fusion report card measures the fix on YOUR prompt and model and shows the result with its honesty badge instead of assuming the fix helps.

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
