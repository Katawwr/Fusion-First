# Handoff — Fusion First rebuild (updated 2026-09-27)

Start the next chat with: **"Read HANDOFF.md and CLAUDE.md, then continue."** Project memory in
`~/.claude/projects/.../memory/` loads automatically. The approved plan is at
`~/.claude/plans/continue-autonomously-untril-manually-robust-naur.md`.

## Where things stand

- Branch `rebuild/agentic-safety-engine`. Everything is committed locally; **never push or publish**.
- Green: `python -m pytest -q` (offline), `ruff check fusion tests scripts app`, frontend lint + vitest
  + build, and the Playwright E2E suite (`npm --prefix frontend run test:e2e`, drives `fusion serve`
  offline). `TRUST_REPORT.md` and `frontend/src/content/evidence.json` are generated
  (`python -m fusion.validate.trust_report`); tests fail if they drift from `evals/`.

## Non-negotiables (also in CLAUDE.md and memory)

- **Zero spend.** Real calls only through local Ollama or the `claude` CLI on subscription auth. Never
  use an API key; never run `claude auth login|logout|setup-token`. Before a subscription-heavy batch
  call `get_usage` (extra usage disabled, 5-hour < 70%, weekly < 60%). The extra-usage meter showed
  £51.06 against £45 (disabled; predates this work) — the user has been told.
- **The `claude` CLI is logged out.** Web live scans need it (Claude grades them) and the picker says
  so; the command-line run engine can grade locally; host subagents work keylessly.
- **One local Ollama job at a time.** The GPU fits one model.
- **Bash heredocs collapse `\\`** — write code with backslashes via Write/Edit.
- **Numbers only from committed evidence** (`evals/claims.yaml`). Never claim the rubric improves
  accuracy (B3), that the fix works on small models (Q3), or that the judge is "calibrated".
- **Pre-register before measuring** (`evals/validation/v1/PREREG_*.md`, `datasets/guard_bench/PREREG_*`);
  never tune on a set after scoring it; a spent held-out set needs a fresh one.
- Downloads need the user's OK: they approved `@playwright/test` (pinned 1.58.2, cached Chromium 1208);
  `npm audit fix` for the react-router advisories is still waiting on them.

## What the evidence says now (all generated into TRUST_REPORT.md)

- **Q1 grader accuracy** (Sonnet host judge vs oracles, 120 llama3.2:1b transcripts): injection 80%,
  leakage 92%; beats regex, not significantly.
- **Q4 / B3:** a plain one-question Sonnet judge is as accurate on the same items (86% vs 87%).
- **Q3 fix, 4 models:** pooled no clear change on attacks, significantly more refusals of safe requests
  (+13 pts); one proven win (Gandalf on qwen2.5:3b), one significant regression (XSTest on llama).
- **Runtime guardrail on real attacks (pre-registered):** stopped 54/69 = 78% (97% of password leaks,
  71% data-stealing, 38% direct-harm hijacks), wrongly blocked 5% of clean transcripts. The strongest
  value evidence: it protects small models where the prompt fix doesn't. A CamelCase bug it found is
  fixed (a6fa0f5); the honest re-measure is registered on fresh transcripts (see In flight).
- **Claude Code guard hook, held-out v3 (blind, scored once at f7d3809):** 5% of benign calls prompted,
  76% of attacks caught. v3 is now spent: any hook rule change needs a fresh v4.

## In flight (the GPU queue — one Ollama job at a time)

1. **Compact-fix run** (pre-registered, `PREREG_compact_fix.md`), resumable:
   `python scripts/run_evidence.py run --n 30 --models llama3.2:1b,qwen2.5:1.5b,gemma3:1b,qwen2.5:3b --arms baseline,hardened,compact --salt fusion-evidence-compact-v1 --exclude-salt fusion-evidence-v1 --max-tokens 600 --max-tokens-safety 256`
   Then: `python scripts/run_evidence.py analyze --n 30 --models <same> --arms baseline,compact --salt fusion-evidence-compact-v1 --exclude-salt fusion-evidence-v1 --out evals/validation/v1/compact_fix.json`
   (emits `prereg_decision`, applied in code); regenerate the Trust Report (its section is ready);
   commit the transcripts too.
2. **Guardrail on fresh transcripts** (`PREREG_guard_on_fresh_transcripts.md`, CPU only, after 1):
   `python scripts/guard_on_transcripts.py --salt fusion-evidence-compact-v1 --exclude-salt fusion-evidence-v1 --preregistration evals/validation/v1/PREREG_guard_on_fresh_transcripts.md --out evals/validation/v1/guard_on_fresh_transcripts.json`
   (read a git snapshot of the transcripts if anything is still appending to them).
3. **Free local grader accuracy** (`PREREG_local_grader.md`): run `je-prob` is prepared in the session
   scratchpad; recreate with `scripts/judge_eval.py prepare --workspace W --run-id je-prob --experiments gandalf,injecagent --models llama3.2:1b`,
   then `grade ... --grader ollama-prob:qwen2.5:7b` and `score ... --grader-label "qwen2.5:7b probability judge (local)" --out evals/validation/v1/judge_eval_prob_qwen7b.json --artifacts evals/validation/v1/judge_eval_prob_qwen7b`.
   Apply the registered floor to `fusion doctor`'s default.
4. **Live smoke of `openai-compat:`** against Ollama's own `/v1` (e.g.
   `openai-compat:http://127.0.0.1:11434/v1#llama3.2:1b`) with a tiny run.

## What this session built (`git log 5ade926..HEAD`)

- Evidence: 4-model Q3; pooled tables; B3; guard v3; guardrail on real attacks; prereg-in-code for the
  compact fix; one-shot scorers; every result re-derivable from committed files.
- `fusion serve` (loopback, Host allowlist, per-launch token, no framing; wheel bundles the frontend).
- Honest capabilities end to end (CLI readiness, fail-closed picker, installed Ollama models, no
  "hosted" option locally, demo labelled an illustration on the bars AND the Prove headline).
- `openai-compat:<url>#<model>` targets (public endpoints need the metered opt-in; never follows
  redirects — the review's critical finding).
- Guard hook: three known bypasses closed. Guardrail: CamelCase read tools fixed.
- Ollama client dials 127.0.0.1 (localhost cost ~2 s/request on Windows).
- Copy: no "one-click fix", no "calibrated" judge; the guardrail's measured result on the landing page
  and README (registered claims).
- Playwright E2E (desktop + phone) + CI job.

## Next backlog

- F4 real Prove re-run with an edited prompt (needs a live backend to be useful).
- A local grader path for web scans, if the probability judge clears its floor.
- Guardrail/hook long tail (tools whose names carry no known verb; droppers split across calls;
  LOLBins; DNS/URL-parameter exfil; sudoers/CA edits) — then fresh held-out sets to measure.
- promptfoo comparator (B4; a re-implemented llm-rubric exists in `fusion/validate/baselines.py`).
- Q4 value ledger (found -> confirmed -> fixed/guarded -> durable).

## Where to look

| What | Where |
|---|---|
| Run engine, gates, oracle cross-check, logs | `fusion/runs/{engine,oracle_check,logs,service,cli}.py` |
| Backends / zero-spend resolver, doctor, targets | `fusion/backends/resolve.py`, `fusion/model/providers/` |
| Local web app + E2E | `fusion/web/serve.py`, `fusion/web/factory.py`, `frontend/src/lib/`, `frontend/e2e/` |
| Guard hook + held-out scoring | `fusion/integrations/claude_hooks.py`, `fusion/validate/guard_heldout.py`, `datasets/guard_bench/` |
| Runtime guardrail + real-transcript measurement | `fusion/guardrail/`, `fusion/validate/guard_on_transcripts.py` |
| Evidence pipeline | `fusion/validate/{experiments,analysis,prereg,judge_eval,b3,trust_report}.py`, `scripts/` |
| Claims registry | `evals/claims.yaml`, `tests/test_claims_backed.py` |
