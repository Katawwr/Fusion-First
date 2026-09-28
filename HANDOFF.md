# Handoff — Fusion First rebuild (updated 2026-09-28)

Start the next chat with: **"Read HANDOFF.md and CLAUDE.md, then continue."** Plan:
`~/.claude/plans/continue-autonomously-untril-manually-robust-naur.md`.

## State

- Branch `rebuild/agentic-safety-engine`, all committed locally. **Never push or publish.**
- Green: `python -m pytest -q` (1422), `ruff check fusion tests scripts app`, frontend vitest (67) + lint +
  build, Playwright E2E (10, desktop + phone), `fusion prove --check all --gate`.
- `TRUST_REPORT.md` and `frontend/src/content/evidence.json` are generated
  (`python -m fusion.validate.trust_report`); tests fail on drift.
- GPU queue: the pre-registered Llama Guard comparison (`PREREG_guard_vs_llama_guard.md`, amended before
  data) — `python scripts/guard_vs_llama_guard.py --out evals/validation/v1/guard_vs_llama_guard.json`
  (resumable; verdicts in `evals/validation/v1/guard_vs_llama_guard/raw.jsonl`). The report and /trust
  sections are already committed; commit the evidence + raw verdicts, regenerate the Trust Report.
  Don't change `fusion/guardrail/` before that commit (the evidence pins rules a6fa0f5).

## Non-negotiables

- Zero spend: local Ollama or the `claude` CLI on subscription only; never an API key; never
  `claude auth login|logout|setup-token`. `get_usage` before subscription-heavy batches.
- The `claude` CLI is logged out (web live scans need it; host subagents work keylessly).
- One local Ollama job at a time.
- Numbers only from committed evidence (`evals/claims.yaml`). Pre-register before measuring; score a
  held-out set once; a spent set needs a fresh one.
- Copy: technical, concise, no repetition or over-explaining (owner, 2026-09-28).
- Write code containing backslashes with Write/Edit, not Bash heredocs.

## Evidence (all in TRUST_REPORT.md)

| Question | Result |
|---|---|
| Grader accuracy (Sonnet host, 120 llama3.2:1b transcripts) | injection 80%, leakage 92%; beats regex, not significantly |
| Rubric vs plain question (B3) | 86% vs 87%: no claim that the rubric improves accuracy |
| Free local grader (qwen2.5:7b prob judge) | FAILED bar: acc 60%/55%, F1 0.50/0.37; worse than regex on leakage. Not recommended |
| Prompt fix, 4 small models | pooled: no clear change on attacks, +13 pts refusals of safe requests |
| Compact fix (pre-registered) | NOT ADOPTED; vs the full fix it let more attacks through on gemma3:1b |
| Runtime guardrail, fresh transcripts (rules a6fa0f5) | 50/70 stopped (71%), 2/170 wrongly blocked (1%); first measurement 54/69 |
| Claude Code hook, held-out v3 | 5% benign prompted, 76% attacks caught (v3 spent) |

## This session (`git log 037027f..HEAD`)

- Evidence: compact fix, local grader, guardrail on fresh transcripts; `openai-compat:` live smoke
  (target path) passed against Ollama `/v1`.
- `fusion doctor` recommends a local grader only if its committed evidence met the bar.
- `prove --gate` (judge floor + `require_before_after_honesty`), `--policy`.
- Fixes: non-inferiority float rounding; Q1 table split by an audit paragraph; /trust stated
  "significant" without direction (now per grader).
- Copy pass across site, README, Trust Report; nav "Use"; then all explanatory lead-ins removed (owner).
- **Any model or workflow** (owner, 2026-09-28): hosted presets `openai:` `hf:` `openrouter:` `together:`
  `groq:` `fireworks:` `mistral-api:` `deepseek:` (user's key + `FUSION_ALLOW_API_SPEND=1`), `anthropic:`,
  `cmd:<command>` (any program; JSON on stdin; template `integrations/examples/fusion_adapter.py`),
  `python:` (`fusion.targets.FunctionModelClient`); any chat target can grade; web "Any model" option.
  `cmd:`/`python:` never from the web page; over MCP only with `FUSION_ALLOW_CMD_TARGETS=1`.
  Live smoke: `cmd:` adapter → llama3.2:1b collected 8/8.

- Also: built-in graders' malformed answers stay pending (finalize no longer aborts); `prove --gate`;
  web scan: Quick/Full attack set, JSON download, report survives refresh, Prove re-run with an edited
  prompt (live only); `og-image.png`.

## Next

1. **Guardrail long tail** (rules unfrozen). Measured misses: consequential tools with no known verb
   (`Manage…`, `Create…`, `Give…`); the read step of data-stealing hijacks (the guard gates sends).
   Any rule change: new prereg, fresh transcripts (new salt; baseline arm, InjecAgent + Gandalf,
   4 models ≈ 240 generations, ~30–40 min GPU at current speed), score once.
5. Judge qualification wiring (`fusion/judge/ledger.py` unused; no `evals/judges/`).
7. promptfoo comparator (B4); garak hitlog ingest; `live.py` / web clients via the resolver.

## Tooling notes

- The in-app browser pane's screenshots time out; use the Playwright MCP (`.playwright-mcp/`).
- `fusion serve` reads `index.html` at launch: restart it after `npm run build`.
- `openai-compat:` against Ollama's `/v1` runs with Ollama's default 4,096-token context; prefer
  `ollama:<model>` for Ollama (Fusion sets 8,192).
- Guardrail diagnostics: `scripts/guard_on_transcripts.py --out <scratch>` re-applies current rules to
  any committed sample (diagnostic only, never evidence).

## Where to look

| What | Where |
|---|---|
| Run engine, gates, oracle cross-check | `fusion/runs/`, `fusion/stats/gate.py` |
| Backends, doctor, targets | `fusion/backends/resolve.py`, `fusion/model/providers/` |
| Pre-registered decisions in code | `fusion/validate/prereg.py` |
| Web app + E2E | `fusion/web/`, `frontend/src/`, `frontend/e2e/` |
| Guard hook, held-out scoring | `fusion/integrations/claude_hooks.py`, `fusion/validate/guard_heldout.py` |
| Runtime guardrail + real-transcript measurement | `fusion/guardrail/`, `fusion/validate/guard_on_transcripts.py` |
| Evidence pipeline + Trust Report | `fusion/validate/`, `scripts/`, `evals/validation/v1/` |
| Claims registry | `evals/claims.yaml`, `tests/test_claims_backed.py` |
