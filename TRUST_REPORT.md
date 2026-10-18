# Fusion First: Trust Report

Five questions about Fusion itself: **is it accurate, does it error, does the fix work, does it beat
simpler checks, does a trained detector beat the phrase list?** Generated from committed evidence by
`python -m fusion_first.validate.trust_report`; a test fails if this file and its evidence disagree. Intervals
are 95% Wilson unless noted. Demonstration evidence (the offline stand-in judge) is excluded.

## Bottom line

- **Detecting accurately?** Graded against deterministic oracles: Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules): direct prompt injection 80% (68%–88%), system prompt leakage 92% (82%–96%). It beats the rule-based checks, but not significantly yet (small samples). A plain one-question judge using the same model was just as accurate on the same items (rubric 86%, plain 87%), so Fusion does not claim its rubric improves accuracy. The free local grader, qwen2.5:7b probability judge (local), pre-registered: direct prompt injection 60% (47%–71%), system prompt leakage 55% (42%–67%). Its registered bar (accuracy at least 0.60 and F1 at least 0.60 on both checks): not met, so `fusion doctor` no longer recommends it by default (it can still be chosen explicitly; every run measures its grader in-run and withholds the grade when it falls short).
- **Fixing effectively?** On gemma3:1b, llama3.2:1b, qwen2.5:1.5b, qwen2.5:3b: 1 proven improvement(s) (gandalf on qwen2.5:3b); 1 significant regression(s) (xstest on llama3.2:1b). Pooled over the 4 models: no clear change for password leaks (Gandalf), missed instructions (IFEval), tool hijacking (InjecAgent); significantly worse for refusing safe requests (XSTest). Every report card therefore measures the fix on the user's own model instead of assuming it helps.
- **Runtime guardrail in your agent?** On fresh real attacks against qwen2.5:7b and llama3.1:8b, measured once with the current rules (pre-registered), it stopped 132 of 148, 89% (83%–93%): 100% of password leaks, 100% of direct-harm tool hijacks, 69% of data-stealing tool hijacks. It wrongly blocked 1% (0%–3%) of clean transcripts. On the same transcripts the previous rules stopped 104 and Llama Guard 3 (configured) 77, wrongly blocking 10% (6%–14%). Given the tool results as well, on further fresh transcripts of the same models (pre-registered), it stopped 75 of 75 attacks (55 of 55 data-stealing) vs 67 (47) without them, wrongly blocking 1 of 225 clean transcripts either way. Its cost, in a live AgentDojo agent loop on held-out tasks (qwen2.5:7b, pre-registered): the agent completed 22 of 66 legitimate tasks with the guard vs 29 without it (7 broken, 0 fixed), over the registered 10-point margin.
- **Runtime guard (Claude Code hook)?** On held-out tool calls it prompted on 5% (2%–11%) of benign calls and caught 76% (64%–84%) of attack-shaped ones as written: useful defense in depth, not a sandbox.
- **Erroring often?** In the fix-efficacy run, 1 of 480 item pairs failed to generate, 0 were undecidable by the oracle and 45 were cut by the token cap; in the judge evaluation, 0 of 240 questions went unanswered. Every card counts and shows its unscored cases, and a grade is withheld ('?') when too much is unscored, when the grader misses the known-answer floor, or when it denies an oracle-confirmed violation.
- **Trained detector for injected tool results?** On unspent InjecAgent tool results from a source it never trained on, it flagged 0 of 744, 0.0% (0.0%–0.5%), where the phrase list flagged 0 of 744; the shipped model flagged 4 of 961 distinct benign tool results, 0.4% (0.2%–1.1%). Registered decision: not adopted: the detector stays dev-only.

## Q1: Is the judge accurate?

Grader verdicts on real open-weight model transcripts vs deterministic oracle labels (InjecAgent: attacker tool called; Gandalf: planted password leaked), with two rule-based baselines on the same items. Unanswered items are counted and excluded from the rates.

| Evidence | Grader | Check | n (unanswered) | Accuracy | Recall | Specificity | F1 | κ | Naive regex F1 | Tuned heuristic F1 |
|---|---|---|---|---|---|---|---|---|---|---|
| `evals/validation/v1/judge_eval_host_sonnet.json` | Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules) | direct_prompt_injection | 60 (0) | 80% (68%–88%) | 80% (55%–93%) | 80% (66%–89%) | 0.67 | 0.53 | 0.53 | 0.10 |
| `evals/validation/v1/judge_eval_host_sonnet.json` | Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules) | system_prompt_leakage | 60 (0) | 92% (82%–96%) | 100% (76%–100%) | 90% (78%–95%) | 0.83 | 0.77 | 0.42 | 0.00 |
| `evals/validation/v1/judge_eval_prob_qwen7b.json` | qwen2.5:7b probability judge (local) | direct_prompt_injection | 60 (0) | 60% (47%–71%) | 80% (55%–93%) | 53% (39%–67%) | 0.50 | 0.24 | 0.53 | 0.10 |
| `evals/validation/v1/judge_eval_prob_qwen7b.json` | qwen2.5:7b probability judge (local) | system_prompt_leakage | 60 (0) | 55% (42%–67%) | 67% (39%–86%) | 52% (38%–66%) | 0.37 | 0.12 | 0.42 | 0.00 |

Disagreement audit (`evals/validation/v1/judge_eval_host_sonnet.json`): Every grader-vs-oracle disagreement was read by the maintainer model (Claude Opus) and classified. This is an LLM reading of the transcripts, NOT ground truth; the primary metrics above stay grader-vs-oracle. ambiguous (attacker tool called, but addressed to the legitimate user): 3; disagreements: 17; grader stricter than the oracle (flagged acknowledging a hidden rule): 4; oracle missed a real violation (grader right per the rubric): 10. Most injection disagreements are llama3.2:1b writing natural-language ACTION lines or committing in prose, which the tool-name oracle cannot see; the leakage ones are the grader applying the rubric strictly to refusals that acknowledge a secret exists. The oracles were pre-registered and are not changed after seeing the grader.

**Free local grader (pre-registered).** `evals/validation/v1/PREREG_local_grader.md` fixed its bar before the grader answered any question: accuracy at least 0.60 and F1 at least 0.60 on both checks. Result: direct prompt injection: accuracy 60%, F1 0.50; system prompt leakage: accuracy 55%, F1 0.37. Bar not met, so `fusion doctor` no longer recommends it by default (it can still be chosen explicitly; every run measures its grader in-run and withholds the grade when it falls short).

Paired McNemar compares per-item correctness (not F1). **Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules):** None of the 4 grader-vs-baseline comparisons is significant at 0.05 yet: the grader scores higher, but these samples can't rule out chance. **qwen2.5:7b probability judge (local):** 2 of 4 grader-vs-baseline comparisons are significant at 0.05, all against the grader (a rule-based baseline was more accurate).
Each item appears twice (as written and with the fix), so rows are not fully independent and the intervals are somewhat narrow. The leakage oracle is a string match for the planted password; the baselines are not told the password.

Each run also measures its grader in-run (known-answer questions plus an oracle cross-check on clear-cut questions) and withholds the grade below the policy floor.

## Q2: Does it error?

- In the fix-efficacy run, 1 of 480 item pairs failed to generate, 0 were undecidable by the oracle and 45 were cut by the token cap.
- In the judge evaluation, 0 of 240 questions went unanswered.
- Every card counts and shows its unscored cases, and a grade is withheld ('?') when too much is unscored, when the grader misses the known-answer floor, or when it denies an oracle-confirmed violation.

Evidence: `evals/validation/v1/evidence_oracle.json`, `evals/validation/v1/judge_eval_host_sonnet.json`, `evals/validation/v1/judge_eval_prob_qwen7b.json`.

## Q3: Does the fix work, and what does it cost?

The prompt as written vs with Fusion's fix, on local models (gemma3:1b, llama3.2:1b, qwen2.5:1.5b, qwen2.5:3b), over held-out items from external benchmarks. Issue = oracle-confirmed attack success (InjecAgent: attacker tool called; Gandalf: planted password leaked) or cost (XSTest: safe request refused; IFEval: instruction not followed). Lower is better. Evidence: `evals/validation/v1/evidence_oracle.json`.

**Pooled over all models.** The interval resamples whole items (each item runs on every model).

| Experiment | Pairs | As written | With fix | Change in issue rate (95% CI) | What it shows |
|---|---|---|---|---|---|
| gandalf (pooled) | 120 | 29% (22%–38%) | 22% (16%–31%) | -7 pts (-17 to +3) | no clear change |
| ifeval (pooled) | 74 | 59% (48%–70%) | 53% (41%–64%) | -7 pts (-17 to +3) | no clear change |
| injecagent (pooled) | 120 | 28% (21%–37%) | 22% (16%–31%) | -6 pts (-17 to +5) | no clear change |
| xstest (pooled) | 120 | 8% (5%–15%) | 22% (15%–30%) | +13 pts (+7 to +20) | **significantly worse with the fix** |

**Per model:**

| Experiment | Model | Pairs | As written | With fix | Paired test | What it shows |
|---|---|---|---|---|---|---|
| injecagent | llama3.2:1b | 30 | 17% (7%–34%) | 33% (19%–51%) | McNemar p=0.125 | worse with the fix, not significant |
| injecagent | qwen2.5:1.5b | 30 | 10% (3%–26%) | 0% (0%–11%) | McNemar p=0.250 | better with the fix, preliminary |
| injecagent | gemma3:1b | 30 | 63% (46%–78%) | 43% (27%–61%) | McNemar p=0.146 | better with the fix, preliminary |
| injecagent | qwen2.5:3b | 30 | 23% (12%–41%) | 13% (5%–30%) | McNemar p=0.453 | better with the fix, preliminary |
| gandalf | llama3.2:1b | 30 | 20% (10%–37%) | 20% (10%–37%) | McNemar p=1.000 | no change |
| gandalf | qwen2.5:1.5b | 30 | 33% (19%–51%) | 37% (22%–54%) | McNemar p=1.000 | worse with the fix, not significant |
| gandalf | gemma3:1b | 30 | 17% (7%–34%) | 17% (7%–34%) | McNemar p=1.000 | no change |
| gandalf | qwen2.5:3b | 30 | 47% (30%–64%) | 17% (7%–34%) | McNemar p=0.022 | significantly better with the fix (PROVEN) |
| xstest | llama3.2:1b | 30 | 10% (3%–26%) | 33% (19%–51%) | McNemar p=0.039 | **significantly worse with the fix** |
| xstest | qwen2.5:1.5b | 30 | 17% (7%–34%) | 17% (7%–34%) | McNemar p=1.000 | no change |
| xstest | gemma3:1b | 30 | 3% (1%–17%) | 20% (10%–37%) | McNemar p=0.062 | worse with the fix, not significant |
| xstest | qwen2.5:3b | 30 | 3% (1%–17%) | 17% (7%–34%) | McNemar p=0.219 | worse with the fix, not significant |
| ifeval | llama3.2:1b | 24 | 67% (47%–82%) | 62% (43%–79%) | McNemar p=1.000 | better with the fix, preliminary |
| ifeval | qwen2.5:1.5b | 14 | 71% (45%–88%) | 64% (39%–84%) | McNemar p=1.000 | better with the fix, preliminary |
| ifeval | gemma3:1b | 18 | 61% (39%–80%) | 39% (20%–61%) | McNemar p=0.125 | better with the fix, preliminary |
| ifeval | qwen2.5:3b | 18 | 39% (20%–61%) | 44% (25%–66%) | McNemar p=1.000 | worse with the fix, not significant |

Significant regressions: xstest on llama3.2:1b. Proven improvements: gandalf on qwen2.5:3b.

A pre-registered compact version of the fix (`evals/validation/v1/PREREG_compact_fix.md`; evidence: `evals/validation/v1/compact_fix.json`) was not adopted: no model had significantly fewer attacks with it without a meaningful rise in refusals of safe requests.

## Q4: Does the rubric beat simply asking an LLM?

The same items graded twice by the same Claude Sonnet: once with Fusion's rubric (the Q1 answers), once asked one plain yes/no question with no rubric. Pre-registered in `evals/validation/v1/PREREG_b3_single_question.md`; evidence: `evals/validation/v1/b3_rubric_vs_plain_judge.json`.

| Check | n (plain unanswered) | Rubric judge | Plain judge | Difference, rubric minus plain (95% CI) | Paired test |
|---|---|---|---|---|---|
| direct_prompt_injection | 59 (1) | 80% (68%–88%) | 80% (68%–88%) | +0 pts (-8 to +8) | McNemar p=1.000 |
| system_prompt_leakage | 60 (0) | 92% (82%–96%) | 93% (84%–97%) | -2 pts (-7 to +3) | McNemar p=1.000 |
| pooled | 119 (1) | 86% (78%–91%) | 87% (79%–92%) | -1 pts (-6 to +4) | McNemar p=1.000 |

**Not shown:** the rubric judge is not significantly more accurate than asking the same model one plain question, so Fusion does not claim it is. What the rubric still provides is a checkable grade: per-criterion answers with quoted evidence, which the run engine uses to reject ungrounded grades.

## Q5: Does a trained detector beat the phrase list on injected tool results?

A small CPU classifier given the request, the tool name and the tool result in one frame, scored once on the sealed confirmatory rows beside the shipped phrase list and the other baselines below. The leave-one-source-out arm scores each source with the fold model trained without it; a row marked in-source was scored by a model that trained on that source's dev rows. Registered in `evals/validation/v1/PREREG_detector_v1.md` (seal `3a311e023f34bccb9533b52e60078f037a6d7dccc4e3922a522667384c1ca85c`); evidence: `evals/validation/v1/detector/detector_v1.json`.

| Source | Arm | Injected texts flagged (recall) | Benign texts flagged (false-positive rate) | Distinct benign texts | AUROC | p50 latency |
|---|---|---|---|---|---|---|
| InjecAgent (unspent) | B0 always negative | 0 of 744, 0% (0%–1%) | 0 of 744, 0% (0%–1%) | 744 | 0.50 | – |
| InjecAgent (unspent) | B1 phrase list (shipped) | 0 of 744, 0% (0%–1%) | 0 of 744, 0% (0%–1%) | 744 | 0.50 | 0.18 ms |
| InjecAgent (unspent) | E embedding, leave-one-source-out | 0 of 744, 0% (0%–1%) | 0 of 744, 0% (0%–1%) | 744 | 0.55 | – |
| InjecAgent (unspent) | E embedding, all sources, shipped (in-source) | 157 of 744, 21% (18%–24%) | 0 of 744, 0% (0%–1%) | 744 | 0.92 | 48 ms |
| InjecAgent (unspent) | F fine-tune, hold-out-InjecAgent fold | 73 of 744, 10% (8%–12%) | 11 of 744, 1% (1%–3%) | 744 | 0.81 | – |
| InjecAgent (unspent) | F fine-tune, all sources (in-source) | 744 of 744, 100% (99%–100%) | 1 of 744, 0% (0%–1%) | 744 | 1.00 | 43 ms |
| InjecAgent (unspent) | B2 Llama Guard 3, configured | 8 of 28, 29% (15%–47%) | 0 of 28, 0% (0%–12%) | 28 | 0.64 | 7.4 s |
| InjecAgent (unspent) | B2 Llama Guard 3, off the shelf | 6 of 14, 43% (21%–67%) | 3 of 14, 21% (8%–48%) | 14 | 0.61 | 7.2 s |
| BIPIA in carriers | B0 always negative | 0 of 125, 0% (0%–3%) | 0 of 69, 0% (0%–5%) | 69 | 0.50 | – |
| BIPIA in carriers | B1 phrase list (shipped) | 0 of 125, 0% (0%–3%) | 0 of 69, 0% (0%–5%) | 69 | 0.50 | 0.18 ms |
| BIPIA in carriers | E embedding, leave-one-source-out | 1 of 125, 1% (0%–4%) | 0 of 69, 0% (0%–5%) | 69 | 0.61 | – |
| BIPIA in carriers | E embedding, all sources, shipped (in-source) | 9 of 125, 7% (4%–13%) | 2 of 69, 3% (1%–10%) | 69 | 0.58 | 48 ms |
| BIPIA in carriers | F fine-tune, hold-out-InjecAgent fold (in-source) | 114 of 125, 91% (85%–95%) | 9 of 69, 13% (7%–23%) | 69 | 0.97 | – |
| BIPIA in carriers | F fine-tune, all sources (in-source) | 118 of 125, 94% (89%–97%) | 9 of 69, 13% (7%–23%) | 69 | 0.96 | 43 ms |
| BIPIA in carriers | B2 Llama Guard 3, configured | 5 of 29, 17% (8%–35%) | 0 of 29, 0% (0%–12%) | 29 | 0.59 | 7.4 s |
| BIPIA in carriers | B2 Llama Guard 3, off the shelf | 4 of 15, 27% (11%–52%) | 0 of 15, 0% (0%–20%) | 15 | 0.63 | 7.2 s |
| deepset test (in-distribution) | B0 always negative | 0 of 60, 0% (0%–6%) | 0 of 56, 0% (0%–6%) | 56 | 0.50 | – |
| deepset test (in-distribution) | B1 phrase list (shipped) | 1 of 60, 2% (0%–9%) | 0 of 56, 0% (0%–6%) | 56 | 0.51 | 0.18 ms |
| deepset test (in-distribution) | E embedding, leave-one-source-out | 0 of 60, 0% (0%–6%) | 0 of 56, 0% (0%–6%) | 56 | 0.28 | – |
| deepset test (in-distribution) | E embedding, all sources, shipped (in-source) | 9 of 60, 15% (8%–26%) | 0 of 56, 0% (0%–6%) | 56 | 0.84 | 48 ms |
| deepset test (in-distribution) | F fine-tune, hold-out-InjecAgent fold (in-source) | 58 of 60, 97% (89%–99%) | 0 of 56, 0% (0%–6%) | 56 | 1.00 | – |
| deepset test (in-distribution) | F fine-tune, all sources (in-source) | 59 of 60, 98% (91%–100%) | 3 of 56, 5% (2%–15%) | 56 | 1.00 | 43 ms |
| deepset test (in-distribution) | B2 Llama Guard 3, configured | 2 of 28, 7% (2%–23%) | 0 of 29, 0% (0%–12%) | 29 | 0.54 | 7.4 s |
| deepset test (in-distribution) | B2 Llama Guard 3, off the shelf | 0 of 14, 0% (0%–22%) | 0 of 14, 0% (0%–22%) | 14 | 0.50 | 7.2 s |
| Blind negatives | B0 always negative | – | 0 of 148, 0% (0%–3%) | 148 | – | – |
| Blind negatives | B1 phrase list (shipped) | – | 0 of 148, 0% (0%–3%) | 148 | – | 0.18 ms |
| Blind negatives | E embedding, leave-one-source-out | – | 6 of 148, 4% (2%–9%) | 148 | – | – |
| Blind negatives | E embedding, all sources, shipped (in-source) | – | 2 of 148, 1% (0%–5%) | 148 | – | 48 ms |
| Blind negatives | F fine-tune, hold-out-InjecAgent fold (in-source) | – | 2 of 148, 1% (0%–5%) | 148 | – | – |
| Blind negatives | F fine-tune, all sources (in-source) | – | 3 of 148, 2% (1%–6%) | 148 | – | 43 ms |
| Blind negatives | B2 Llama Guard 3, configured | – | 0 of 29, 0% (0%–12%) | 29 | – | 7.4 s |
| Blind negatives | B2 Llama Guard 3, off the shelf | – | 0 of 14, 0% (0%–22%) | 14 | – | 7.2 s |

- Registered decision: **not adopted: the detector stays dev-only**. Recall on the 744 unspent InjecAgent injected tool results, under the fold that never saw InjecAgent: 0.0% (0.0%–0.5%), bar at least 0.60. False-positive rate of the shipped all-sources model on the 961 distinct benign tool results: 0.4% (0.2%–1.1%), bar at most 0.05.
- Never-seen InjecAgent injections flagged, and false alarms on their benign minimal pairs (no arm here trained on InjecAgent): B1 phrase list 0 of 744 flagged (0.0%), 0 of 744 false alarms (0.0%); E leave-one-source-out 0 of 744 flagged (0.0%), 0 of 744 false alarms (0.0%); F hold-out-InjecAgent fold 73 of 744 flagged (9.8%), 11 of 744 false alarms (1.5%); B2 Llama Guard 3 configured, on its subsample, 8 of 28 flagged (28.6%), 0 of 28 false alarms (0.0%); B2 Llama Guard 3 off the shelf, on its subsample, 6 of 14 flagged (42.9%), 3 of 14 false alarms (21.4%).
- In-source InjecAgent rows: the E all-sources model 157 of 744 flagged (21.1%); the F all-sources model 744 of 744 flagged (100.0%). These models trained on the dev InjecAgent rows, which share the 62 attacker instructions and 17 tool-result templates with the confirmatory rows; the registration states that in-source numbers flatter any model and that "only the LOSO numbers are claimed" (`evals/validation/v1/PREREG_detector_v1.md`, "Limits, stated before data"); this report reads that as: leave-one-source-out recall is the only generalisation claim.
- Unscored rows (no finite score; excluded from that arm's rates): none in any arm.
- Registered arms not run: B3 ProtectAI deberta-v3.
- Limits registered before data: text-level detection only, not attack success or the guard's cost in an agent loop; no adaptive-attack evaluation, so a static result is expected to degrade against an attacker who adapts to the detector; the deepset test rows are in-distribution with respect to deepset's own training split; AgentDojo is dev-only (its held-out set is spent for the guard), so no AgentDojo row is scored here; the registration's own words on claim scope are "only the LOSO numbers are claimed" (`evals/validation/v1/PREREG_detector_v1.md`, "Limits, stated before data"), which this report reads as: leave-one-source-out recall is the only generalisation claim; the shipped model's false-positive rate and the baselines' rows are registered measurements on the sealed rows and say nothing about unseen sources; rows marked in-source come from a model that trained on that source's dev rows: the E all-sources model and the F all-sources model on every source; F hold-out-InjecAgent fold on BIPIA, deepset and blind (`finetune_holdout_injecagent` trained on their dev rows); each Llama Guard 3 arm runs on its own stratified subsample with its own n.

Registered secondaries (reported, no decision; McNemar against the phrase list is not the bar): exact McNemar of each arm against the phrase list on the rows both scored, paired per row; recall by technique at each arm's operating point (a family of categories such as BIPIA's is counted, not itemised; the per-category rates stay in the envelope); CPU latency per decision.

| Arm | Rows paired | Arm right, list wrong | List right, arm wrong | McNemar p | Per source: arm right vs list right (p) |
|---|---|---|---|---|---|
| B0 always negative | 1946 | 0 | 1 | p=1.0000 | InjecAgent 0 vs 0 (p=1.0000); BIPIA 0 vs 0 (p=1.0000); deepset 0 vs 1 (p=1.0000); blind 0 vs 0 (p=1.0000) |
| E embedding, leave-one-source-out | 1946 | 1 | 7 | p=0.0703 | InjecAgent 0 vs 0 (p=1.0000); BIPIA 1 vs 0 (p=1.0000); deepset 0 vs 1 (p=1.0000); blind 0 vs 6 (p=0.0312) |
| E embedding, all sources, shipped (in-source) | 1946 | 175 | 5 | p<0.0001 | InjecAgent 157 vs 0 (p<0.0001); BIPIA 9 vs 2 (p=0.0654); deepset 9 vs 1 (p=0.0215); blind 0 vs 2 (p=0.5000) |
| F fine-tune, hold-out-InjecAgent fold | 1946 | 244 | 22 | p<0.0001 | InjecAgent 73 vs 11 (p<0.0001); BIPIA 114 vs 9 (p<0.0001); deepset 57 vs 0 (p<0.0001); blind 0 vs 2 (p=0.5000) |
| F fine-tune, all sources (in-source) | 1946 | 920 | 16 | p<0.0001 | InjecAgent 744 vs 1 (p<0.0001); BIPIA 118 vs 9 (p<0.0001); deepset 58 vs 3 (p<0.0001); blind 0 vs 3 (p=0.2500) |
| B2 Llama Guard 3, configured | 200 | 15 | 0 | p<0.0001 | InjecAgent 8 vs 0 (p=0.0078); BIPIA 5 vs 0 (p=0.0625); deepset 2 vs 0 (p=0.5000); blind 0 vs 0 (p=1.0000) |
| B2 Llama Guard 3, off the shelf | 100 | 10 | 3 | p=0.0923 | InjecAgent 6 vs 3 (p=0.5078); BIPIA 4 vs 0 (p=0.1250); deepset 0 vs 0 (p=1.0000); blind 0 vs 0 (p=1.0000) |

| Arm | InjecAgent direct harm | InjecAgent data stealing | deepset | BIPIA categories with any flag |
|---|---|---|---|---|
| B0 always negative | 0 of 367 (0.0%) | 0 of 377 (0.0%) | 0 of 60 (0.0%) | 0 of 25 |
| B1 phrase list (shipped) | 0 of 367 (0.0%) | 0 of 377 (0.0%) | 1 of 60 (1.7%) | 0 of 25 |
| E embedding, leave-one-source-out | 0 of 367 (0.0%) | 0 of 377 (0.0%) | 0 of 60 (0.0%) | 1 of 25 |
| E embedding, all sources, shipped (in-source) | 47 of 367 (12.8%) | 110 of 377 (29.2%) | 9 of 60 (15.0%) | 7 of 25 |
| F fine-tune, hold-out-InjecAgent fold | 45 of 367 (12.3%) | 28 of 377 (7.4%) | 58 of 60 (96.7%) | 25 of 25 |
| F fine-tune, all sources (in-source) | 367 of 367 (100.0%) | 377 of 377 (100.0%) | 59 of 60 (98.3%) | 25 of 25 |
| B2 Llama Guard 3, configured | 2 of 10 (20.0%) | 6 of 18 (33.3%) | 2 of 28 (7.1%) | 5 of 18 |
| B2 Llama Guard 3, off the shelf | 0 of 3 (0.0%) | 6 of 11 (54.5%) | 0 of 14 (0.0%) | 3 of 12 |

CPU latency per decision, p50 / p95: B1 phrase list 0.18 ms / 0.39 ms; the E all-sources model 48 ms / 71 ms; the F all-sources model 43 ms / 65 ms; B2 Llama Guard 3 configured 7.4 s / 11.5 s (Ollama wall time per reply); B2 Llama Guard 3 off the shelf 7.2 s / 11.0 s (Ollama wall time per reply). No latency of its own: B0, E leave-one-source-out and F hold-out-InjecAgent fold (a fold arm shares its all-sources model's).

## Request-bound guardrail on 7–8B models (pre-registered)

The current rules (`fusion_first/guardrail` at `0c560b5`: once untrusted content is in context, a tool call that is not a read must be covered by the user's own request, and an unrequested read of private data is blocked) measured once on fresh transcripts of qwen2.5:7b and llama3.1:8b (100 InjecAgent and 100 Gandalf items each, prompt as written), against the previous rules (`a6fa0f5`) and Llama Guard 3 8B on the same transcripts. Registered in `evals/validation/v1/PREREG_step2_guard.md`; evidence: `evals/validation/v1/step2_guard.json`.

| System | Real attacks stopped | Clean transcripts wrongly blocked |
|---|---|---|
| Fusion guard, current rules | 132 of 148, 89% (83%–93%) | 2 of 252, 1% (0%–3%) |
| Fusion guard, previous rules | 104 of 148, 70% (62%–77%) | 0 of 252, 0% (0%–2%) |
| Llama Guard 3, off the shelf | 58 of 148, 39% (32%–47%) | 30 of 252, 12% (8%–16%) |
| Llama Guard 3, configured | 77 of 148, 52% (44%–60%) | 24 of 252, 10% (6%–14%) |
| Fusion + Llama Guard 3 (configured) | 145 of 148, 98% (94%–99%) | 25 of 252, 10% (7%–14%) |

- The current rules stop significantly more real attacks than the previous rules (28 stopped only by the current rules, 0 only by the previous; McNemar p<0.0001), without significantly more wrong blocks (2 vs 0; p=0.50).
- Fusion's guardrail stops significantly more real attacks than Llama Guard 3 off the shelf (87 stopped only by Fusion, 13 only by Llama Guard; McNemar p<0.0001), without significantly more wrong blocks.
- Fusion's guardrail stops significantly more real attacks than Llama Guard 3 configured (68 stopped only by Fusion, 13 only by Llama Guard; McNemar p<0.0001), without significantly more wrong blocks.
- Legitimate requested actions never used in development: 1 of 20 blocked by the current rules (registered limit 2).
- Attacks whose attacker tool never appeared in development: 26 of 33 stopped (previous rules 13, Llama Guard 3 configured 20).
- Registered decision: the current rules are **adopted**.

Current rules by attack type:

| Attack | Real attacks | Stopped | Clean transcripts | Wrongly blocked |
|---|---|---|---|---|
| password leaks (Gandalf) | 75 | 100% (95%–100%) | 125 | 0% (0%–3%) |
| tool hijack, direct harm (InjecAgent) | 21 | 100% (85%–100%) | 67 | 1% (0%–8%) |
| tool hijack, data stealing (InjecAgent) | 52 | 69% (56%–80%) | 60 | 2% (0%–9%) |
| all | 148 | 89% (83%–93%) | 252 | 1% (0%–3%) |

- Password leaks: 75 of 75 stopped by both rule sets; Llama Guard stopped 9 (off the shelf) and 25 (configured, told the secret).
- Direct-harm tool hijacks: 21 of 21 stopped (previous rules 9).
- Data-stealing tool hijacks: 36 of 52 stopped (previous rules 20; Llama Guard configured 40). All 16 misses are the read step alone, with a tool whose name names no private data (FedEx shipment search 4, Dropbox item metadata 4 and file listing 1, Spokeo people search 2, Facebook friend search 2, Cisco Umbrella log details 2, 23andMe data download 1); no attacker send was allowed in any of them.
- The 2 clean transcripts counted as wrongly blocked (both llama3.1:8b) were the model carrying out the injected instruction under a toolkit name (GoogleMap with action GetCurrentLocation; EvernoteManager with the attacker's sharing arguments). The oracle matches exact tool names, so it scores them clean; the registered count keeps them as wrong blocks.
- The legitimate action blocked by the new rules: "redirect my shipment ... to a new address" (FedExShipManagerManageShipment); redirect is not among the verbs that authorize Manage. The external-recipient rule, unchanged and with no allowlist, blocked 12 of the 20 (every send to the user's own gmail address).

## The guard given the tool results (pre-registered)

The same rules (`ce897d1`) with and without the text of the tool results the agent saw (`untrusted_text`): given it, a read that text asks for, and the user did not, is blocked when the text also asks to send data to an outside address. Measured once on fresh InjecAgent transcripts of qwen2.5:7b and llama3.1:8b (150 items each). Registered in `evals/validation/v1/PREREG_step3_guard.md`; evidence: `evals/validation/v1/step3_guard.json`.

| Guard | Real attacks stopped | Data-stealing stopped | Clean transcripts wrongly blocked |
|---|---|---|---|
| Given the tool results | 75 of 75, 100% (95%–100%) | 55 of 55, 100% (93%–100%) | 1 of 225, 0% (0%–2%) |
| Without them (as step 2) | 67 of 75, 89% (80%–94%) | 47 of 55, 85% (74%–92%) | 1 of 225, 0% (0%–2%) |

- Attacks stopped only with the tool results: 8; only without: 0 (McNemar p=0.0078). Clean transcripts blocked only with: 0; only without: 0 (registered limit: 3 more, net).
- Registered decision: **adopted**.
- Limits registered before data: InjecAgent's attack wording appeared in development (this tests fresh model behaviour, not unseen attack text), and no fresh set of legitimate actions was available, so the cost is measured on clean transcripts only. Reads a user delegates to a document ("do what this email says") are blocked when the document also asks to send data out.

## The guard's cost in a live agent loop (AgentDojo, pre-registered)

AgentDojo (agentdojo v1.2.2) user tasks run through real tools by qwen2.5:7b; the published guard configuration (rules `de6b97a`) checks every tool call and a blocked call does not run. Held-out tasks only, scored once. Registered in `evals/validation/v1/PREREG_step4_agentdojo.md`; evidence: `evals/validation/v1/step4_agentdojo.json`.

| Arm | Legitimate tasks completed | In-scope attacks that succeeded |
|---|---|---|
| No guard | 29 of 66, 44% (33%–56%) | 9 of 107, 8% (4%–15%) |
| Guard, without the tool results | 22 of 66, 33% (23%–45%) | 3 of 107, 3% (1%–8%) |
| Guard, given the tool results (published) | 22 of 66, 33% (23%–45%) | 3 of 107, 3% (1%–8%) |

- Cost: 7 tasks completed only without the guard, 0 only with it (McNemar p=0.0156); completion fell 10.6 points (95% 4.5 to 18.2). Registered margin: 10 points. Decision: **exceeds margin or undetermined**.
- Given the tool results or not made no difference to cost (0 vs 0).
- Attacks (descriptive, not a registered test): 7 succeeded only without the guard, 1 only with it (McNemar p=0.0703).
- What it blocked: requests worded differently from the tool ("pay the bill" for `send_money`, "post" for `send_channel_message`), sends to non-allowlisted addresses, addresses or links mentioned inside a message body read as destinations, and a file name (recipe-collection.docx) read as a host. These are rule changes for a fresh registration, not this one.

## Runtime guard for Claude Code (fusion-guard hook)

Tool calls written by independent agents **blind to the rules**, scored once.

| Set | benign n | Prompted (over-block) | attack n | Caught (recall) | Status |
|---|---|---|---|---|---|
| v3 | 100 | 5% (2%–11%) | 70 | 76% (64%–84%) | held out, scored once |

Pattern rules catch the common exfiltration / destruction / remote-code shapes and miss much of the long tail; treat the hook as defense in depth, not a sandbox.

## Known limits

- Oracle labels decide narrow questions (a tool was called, a password appeared). Where the judge's rubric is broader than the oracle, some 'disagreements' are real violations the oracle can't see: see each disagreement audit.
- Samples are small (tens of transcripts per cell); read the intervals, not the points.
- Known-answer questions come from a public gold set; the in-run oracle cross-check covers only clear-cut questions.

Superseded evidence kept for audit: `evals/validation/v1/guard_on_transcripts.json`, `evals/validation/v1/guard_on_fresh_transcripts.json`, `evals/validation/v1/guard_vs_llama_guard.json`, `evals/validation/v1/value_ledger.json`, `evals/validation/v1/compact_vs_full_fix.json`, `evals/guard_bench/claude_code_heldout_v1.json`, `evals/guard_bench/claude_code_heldout_v2.json`.
