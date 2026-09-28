# Handoff — Fusion First rebuild (updated 2026-09-28, end of second session)

Start the next chat with: **"Read HANDOFF.md and CLAUDE.md, then continue."** At 85% context this happens
automatically (CLAUDE.md, "Context handoff"). Plan: `~/.claude/plans/continue-autonomously-untril-manually-robust-naur.md`.

## State

- Branch `rebuild/agentic-safety-engine`, all committed locally. **Never push or publish.**
- Green at last run: `python -m pytest -q` (1,612), `ruff check fusion tests scripts app`, frontend vitest (83)
  + lint + build, Playwright E2E (11).
- `TRUST_REPORT.md` and `frontend/src/content/evidence.json` are generated
  (`python -m fusion.validate.trust_report`); tests fail on drift.
- Ollama models: llama3.2:1b, qwen2.5:1.5b, gemma3:1b, qwen2.5:3b, qwen2.5:7b, llama3.1:8b, llama-guard3:8b.
  GPU idle.
- **Step 2 scored and committed** (c6fe064; `evals/validation/v1/step2_guard.json`, re-derived by
  `tests/test_step2_guard_evidence.py`): the request-bound rules (0c560b5) are ADOPTED. Headline now in the
  README, Trust Report and /trust (3f5835b).
- Since the measured rules, two fixes (dc10cb3): configured secrets match in any letter case; "redirect"
  authorizes Manage tools. Both only tighten or widen by construction; the numbers above are for 0c560b5 and
  a new claim about the current rules needs fresh transcripts.
- `.git/worktrees/prior-a6fa0f5` is an empty leftover (sandbox denied deletion); `git worktree prune` clears it.

## Non-negotiables

- Zero spend for our build/testing: local Ollama or the `claude` CLI on subscription only; never an API key;
  never `claude auth login|logout|setup-token`. End users may bring their own keys (hosted presets).
- The `claude` CLI is logged out (web live scans that grade with it can't run here; host subagents work).
- One local Ollama job at a time.
- Numbers only from committed evidence (`evals/claims.yaml`). Pre-register before measuring; score once;
  a spent set needs a fresh one; amendments only before data, written into the prereg.
- Copy: technical, concise, no lead-ins or over-explaining (owner). Nav item is "Use".
- Write code containing backslashes with Write/Edit, not Bash heredocs.

## Evidence (all in TRUST_REPORT.md; unchanged this session)

| Question | Result |
|---|---|
| Grader accuracy (Sonnet host, 120 llama3.2:1b transcripts) | injection 80%, leakage 92%; beats regex, not significantly |
| Rubric vs plain question (B3) | 86% vs 87%: no claim that the rubric improves accuracy |
| Free local grader (qwen2.5:7b prob judge) | FAILED bar: acc 60%/55%, F1 0.50/0.37. Not recommended |
| Prompt fix, 4 small models | pooled: no clear change on attacks, +13 pts refusals of safe requests |
| Compact fix | NOT ADOPTED |
| Runtime guardrail, fresh transcripts (rules a6fa0f5) | 50/70 stopped (71%), 2/170 wrongly blocked (1%) |
| Guardrail vs Llama Guard 3 8B (same transcripts) | off the shelf 33/70, 15% wrongly blocked (Fusion significantly better); configured 44/70, 16% (no significant difference). Leaks: Fusion 37/37 vs 20/37. Tool hijacks: Fusion 13/33 vs 24/33. Both layers: 63/70, 17% |
| Claude Code hook, held-out v3 | 5% benign prompted, 76% attacks caught (v3 spent) |
| **Step 2: request-bound guard (0c560b5), qwen2.5:7b + llama3.1:8b, 148 attacks / 252 clean** | **132/148 (89%), 2/252 (1%)**; previous rules 104/148, 0/252 (28 vs 0, p=7e-9); Llama Guard off the shelf 58/148, 30/252; configured 77/148, 24/252 (both significantly worse). Leaks 75/75, direct harm 21/21, data stealing 36/52 (LG configured 40/52). Held-out legitimate actions 1/20 blocked. Unseen attacker tools 26/33. ADOPTED |

## This session (`git log 4e344f3..HEAD`)

- **Step 1 done (dev):** the guard binds tool calls to the user's request (18e424c, 0c560b5). Under
  `require_authorization` or `untrusted_context=True`, a call not shown to be a read needs the request to use
  one of its action verbs (synonyms, verb position, idioms excluded) AND name what it touches (object words,
  service, or the call's argument values); after untrusted content an unrequested private-data read is
  blocked; missing request or tool name fails closed. Default posture unchanged. `user_identities` config
  lets "email it to me" pass. A red-team review found 21 issues; all fixed, kept in `tests/test_guard_redteam.py`.
  DIAGNOSTIC on spent samples (`scripts/guard_dev.py`, never quote): tool hijacks stopped compact 29/33
  (was 13/33), v1 33/34; clean wrongly blocked 0/87, 1/86. Remaining misses: same-service reads
  (GitHubGetUserDetails after a GitHub request) and FedEx shipment searches (not in the private-data list).
- **Harness v2** (`fusion/validate/guard_on_transcripts.py`): the guard gets the user's instruction only (v1
  passed the injected tool result too), `untrusted_context=True`, scenario tool spelling. `HARNESS` string.
- **Step 2 benign set:** `fusion/validate/benign_actions.py`: InjecAgent attacker cases with the user asking
  (62) + InjecAgent user cases (17). 42 `dev` (tools seen in v1/compact) + 17 user cases; **20 `heldout` sealed**
  (never run through the guard). DIAGNOSTIC dev: new rules block 1/21 direct-harm actions (TerminalExecute for
  "move files"), 0/17 user cases; every data-stealing send to the user's gmail is blocked by the pre-existing
  external-recipient rule (no allowlist in that config).
- **Step 3 (power, `scripts/power_plan.py`, from committed effect sizes):** fix reduces attacks: ~600 pairs for
  80% power (not feasible here); fix adds refusals (XSTest): 150 items; guard vs configured Llama Guard at the
  old discordance: ~600 attacks, but a large gap (0.25 vs 0.05 of attacks) needs ~50–80.
- **Step 4 (timing, `scripts/time_generations.py`, DIAGNOSTIC):** qwen2.5:7b 1.3–1.4 tok/s at num_ctx 4096 or
  8192 (48% vs 45% on GPU: no gain). InjecAgent ~70 s/generation, full 256-token answers ~190–205 s.
  Estimate, baseline arm only: 150 InjecAgent + 150 Gandalf ≈ 8 h, Llama Guard verdicts ≈ 3 h; + XSTest both
  arms (150) ≈ 16 h.
- **Context handoff automation** (5657a66): hook + routines `fusion-continue-a/-b` (CLAUDE.md).

## Next

1. Data-stealing reads are the remaining gap (all 16 step-2 misses: a read whose tool names no private data,
   e.g. shipment search, file metadata/listing, people or friend search, security logs). Options: gate every
   unrequested read after untrusted content when the conversation also carries an injected send instruction,
   or widen the private-data taxonomy (dev only; spent samples). Any change needs a fresh registration.
2. Oracle gap for future preregs: a model may call a toolkit name with the action in the arguments (`GoogleMap`
   + `{"action": "GetCurrentLocation"}`); the exact-name oracle scores that clean. Count a call whose name is a
   prefix of an attacker tool and whose arguments name the rest as an attack (register it before use).
3. Claude Code hook: capture the user's prompt (UserPromptSubmit) so MCP calls after taint can use the request
   binding; needs a fresh held-out set (v4) before any claim.
4. Owner's open decisions below.

## Open decisions (owner)

- Reposition as "measure + guard" with the fix demoted (recommended: step 2 makes the guard the strongest
  evidence, 89% stopped vs Llama Guard's 52%; proving the fix reduces attacks needs ~600 pairs, ~33 h per model).
  Not applied.
- Fix arms (not in step 2): 300 pairs per model (the step-2 items + hardened arm, ~8–9 h per model) detect a
  moderate or strong fix effect (99–100% power) but not the small 1–3B one (56%); 600 pairs ≈ 33 h per model.
- Decided 2026-09-28: second model llama3.1:8b (pulled); named recipients stay blocked unless allowlisted.
- Routines `fusion-continue-a/-b` run with their stored permission mode and medium effort: set auto mode in the
  sidebar (Scheduled) for unattended continuations.

## Tooling notes

- In-app browser screenshots time out; use the Playwright MCP (`.playwright-mcp/`; `file:` URLs blocked:
  stage a page in `frontend/dist` and load it from `fusion serve`).
- `fusion serve` reads `index.html` at launch: restart it after `npm run build`.
- `openai-compat:` against Ollama's `/v1` gets a 4,096-token context; prefer `ollama:` for Ollama.
- `scripts/guard_on_transcripts.py --out <scratch>` re-applies current rules to any sample (diagnostic only);
  `scripts/guard_dev.py` is the dev readout (spent samples + benign dev only).
- Hooks load at session start; settings edits apply to new sessions.

## Where to look

| What | Where |
|---|---|
| Specs, doctor, presets | `fusion/backends/resolve.py`, `fusion/backends/presets.py`, `fusion/model/providers/` |
| Run engine, gates | `fusion/runs/`, `fusion/stats/gate.py` |
| Pre-registered decisions in code | `fusion/validate/prereg.py`, `fusion/validate/llama_guard.py` |
| Runtime guardrail + measurements | `fusion/guardrail/`, `fusion/validate/guard_on_transcripts.py`, `fusion/validate/benign_actions.py`, `scripts/guard_*.py` |
| Web app + E2E | `fusion/web/`, `frontend/src/`, `frontend/e2e/` |
| Evidence + Trust Report | `evals/validation/v1/`, `fusion/validate/trust_report.py` |
| Claims registry | `evals/claims.yaml`, `tests/test_claims_backed.py` |
