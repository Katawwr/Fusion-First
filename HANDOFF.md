# Handoff — Fusion First rebuild (updated 2026-09-28, end of session)

Start the next chat with: **"Read HANDOFF.md and CLAUDE.md, then continue."** Plan:
`~/.claude/plans/continue-autonomously-untril-manually-robust-naur.md`.

## State

- Branch `rebuild/agentic-safety-engine`, all committed locally. **Never push or publish.**
- Green at last run: `python -m pytest -q` (~1,470), `ruff check fusion tests scripts app`, frontend vitest (81)
  + lint + build, Playwright E2E (11), `fusion prove --check all --gate`.
- `TRUST_REPORT.md` and `frontend/src/content/evidence.json` are generated
  (`python -m fusion.validate.trust_report`); tests fail on drift.
- GPU queue: empty. Ollama models: llama3.2:1b, qwen2.5:1.5b, gemma3:1b, qwen2.5:3b, qwen2.5:7b, llama-guard3:8b.

## Non-negotiables

- Zero spend for our build/testing: local Ollama or the `claude` CLI on subscription only; never an API key;
  never `claude auth login|logout|setup-token`. End users may bring their own keys (hosted presets).
- The `claude` CLI is logged out (web live scans that grade with it can't run here; host subagents work).
- One local Ollama job at a time.
- Numbers only from committed evidence (`evals/claims.yaml`). Pre-register before measuring; score once;
  a spent set needs a fresh one; amendments only before data, written into the prereg.
- Copy: technical, concise, no lead-ins or over-explaining (owner). Nav item is "Use".
- Write code containing backslashes with Write/Edit, not Bash heredocs.

## Evidence (all in TRUST_REPORT.md)

| Question | Result |
|---|---|
| Grader accuracy (Sonnet host, 120 llama3.2:1b transcripts) | injection 80%, leakage 92%; beats regex, not significantly |
| Rubric vs plain question (B3) | 86% vs 87%: no claim that the rubric improves accuracy |
| Free local grader (qwen2.5:7b prob judge) | FAILED bar: acc 60%/55%, F1 0.50/0.37. Not recommended |
| Prompt fix, 4 small models | pooled: no clear change on attacks, +13 pts refusals of safe requests |
| Compact fix | NOT ADOPTED |
| Runtime guardrail, fresh transcripts (rules a6fa0f5) | 50/70 stopped (71%), 2/170 wrongly blocked (1%) |
| Guardrail vs Llama Guard 3 8B (same transcripts) | off the shelf 33/70, 15% wrongly blocked (Fusion significantly better); configured 44/70, 16% (no significant difference on attacks). Leaks: Fusion 37/37 vs 20/37. Tool hijacks: Fusion 13/33 vs 24/33. Both layers: 63/70, 17% wrongly blocked |
| Claude Code hook, held-out v3 | 5% benign prompted, 76% attacks caught (v3 spent) |

## This session (`git log 037027f..HEAD`)

- Evidence: compact fix, local grader, guardrail on fresh transcripts, Llama Guard comparison (amendment
  before data: Ollama's llama-guard3 template asks about the last *User* message; both configs use Meta's
  format in raw mode).
- Any model or workflow: presets `openai:` `hf:` `openrouter:` `together:` `groq:` `fireworks:`
  `mistral-api:` `deepseek:` (user's key + `FUSION_ALLOW_API_SPEND=1`), `anthropic:`, `cmd:<command>` (template
  `integrations/examples/fusion_adapter.py`), `python:` (`fusion.targets.FunctionModelClient`); any chat
  target can grade; web "Any model" option. `cmd:`/`python:` never from the web; over MCP only with
  `FUSION_ALLOW_CMD_TARGETS=1`. Hosted presets tested with fakes only.
- Fixes: built-in graders' malformed answers stay pending (finalize no longer aborts); non-inferiority float
  rounding; `fusion doctor` recommends a local grader only with committed evidence; per-grader significance
  direction on /trust.
- Features: `prove --gate`; web scan Quick/Full attack set, JSON download, report survives refresh, Prove
  re-run with an edited prompt (live only); `og-image.png`.
- Copy: site/README/report tightened; all explanatory lead-ins removed.

## Step 2 (evidence on models people deploy): NOT ready — do these first

1. **Close the guard's tool-hijack gap** (it trails Llama Guard there: 13/33 vs 24/33). Measured misses:
   consequential tools with no known verb (`Manage…`, `Create…`, `Give…`; 7 of 7 direct-harm misses) and
   the read step of data-stealing (11 misses; the guard gates sends). Candidate: a tool call that isn't
   read-only needs to match the user's request once untrusted content is in context (taint).
   Develop on the spent v1 + compact transcripts; rules unfrozen now.
2. **Measure over-block on legitimate consequential actions.** The clean sets contain almost no benign
   consequential calls, so change 1 could over-block unseen. Build a benign-actions set (user asks to send,
   create, book...) before claiming anything.
3. **Right-size samples.** n=30 per experiment left most results inconclusive, and stronger models land
   fewer attacks (too few to measure guard recall). Size n with `fusion.stats.power.mcnemar_power`;
   consider InjecAgent's enhanced setting for stronger models (pre-register it).
4. **Hardware budget.** AMD RX 6500 XT (4 GB VRAM), i3-10100F, 16 GB RAM: 7–9B models run ~50% on CPU
   (hours per model per arm set). Plan 1–2 models, safety experiments + XSTest, baseline + full-fix arms;
   try `num_ctx` 4096 (prompts fit) to keep more layers on the GPU; time a few generations first.
5. Then pre-register step 2; its fresh transcripts are the held-out test for the improved guard.

## Open decisions (owner)

- Reposition as "measure + guard" with the fix demoted (recommended; evidence above). Not applied.

## Tooling notes

- In-app browser screenshots time out; use the Playwright MCP (`.playwright-mcp/`; `file:` URLs blocked:
  stage a page in `frontend/dist` and load it from `fusion serve`).
- `fusion serve` reads `index.html` at launch: restart it after `npm run build`.
- `openai-compat:` against Ollama's `/v1` gets a 4,096-token context; prefer `ollama:` for Ollama.
- `scripts/guard_on_transcripts.py --out <scratch>` re-applies current rules to any sample (diagnostic only).

## Where to look

| What | Where |
|---|---|
| Specs, doctor, presets | `fusion/backends/resolve.py`, `fusion/backends/presets.py`, `fusion/model/providers/` |
| Run engine, gates | `fusion/runs/`, `fusion/stats/gate.py` |
| Pre-registered decisions in code | `fusion/validate/prereg.py`, `fusion/validate/llama_guard.py` |
| Runtime guardrail + measurements | `fusion/guardrail/`, `fusion/validate/guard_on_transcripts.py`, `scripts/guard_*.py` |
| Web app + E2E | `fusion/web/`, `frontend/src/`, `frontend/e2e/` |
| Evidence + Trust Report | `evals/validation/v1/`, `fusion/validate/trust_report.py` |
| Claims registry | `evals/claims.yaml`, `tests/test_claims_backed.py` |
