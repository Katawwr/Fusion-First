# Pre-registration: accuracy of the free local grader (qwen2.5:7b probability judge)

Registered 2026-09-27, before the grader answered any of these questions.

## Why

`fusion doctor` recommends `--grader ollama-prob:qwen2.5:7b` by default to anyone without a logged-in
`claude` CLI, and the web page now points there too. Its accuracy against deterministic oracles has
never been measured.

## Design (fixed before data)

- **Items:** the 120 Q1 transcripts (llama3.2:1b; InjecAgent graded as `direct_prompt_injection`,
  Gandalf as `system_prompt_leakage`; both arms), prepared as run `je-prob` with
  `scripts/judge_eval.py prepare`. Labels: the same deterministic oracles.
- **Grader:** `ollama-prob:qwen2.5:7b` through `scripts/judge_eval.py grade` (the production
  probability judge; per-criterion yes/no log-probabilities). One pass.
- **Outcomes:** per check, accuracy, recall, specificity, F1 and kappa against the oracles, with 95%
  Wilson intervals; unanswered questions counted and excluded. Secondary: paired McNemar against the
  committed Sonnet host-judge answers on the same items.
- **Decision rule:** it stays the default free grader only if BOTH checks meet the repo's policy
  floor (`evals/policy.yaml`: accuracy >= 0.60 and F1 >= 0.60). Otherwise `fusion doctor` stops
  recommending it by default and the docs say why.
