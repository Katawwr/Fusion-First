# Handoff — Fusion First rebuild (updated 2026-09-29, fourth session)

Start the next chat with: **"Read HANDOFF.md and CLAUDE.md, then continue."** At 85% context the hook asks
for a handoff (CLAUDE.md, "Context handoff"): a regular session via `start_session` if the app exposes it
(it doesn't yet), otherwise ask the owner to open a new chat. **Never a routine or scheduled task** (owner).
Plans: `~/.claude/plans/continue-autonomously-untril-manually-robust-naur.md` (master);
`~/.claude/plans/measure-guard-reposition.md` and `~/.claude/plans/guard-replay.md` (third session's, done;
ledgers with every ruling in the gitignored `.superpowers/sdd/<plan>/progress.md`).

## State

- Branch `rebuild/agentic-safety-engine`, all committed locally, no git remote. Never push. Publishing to
  PyPI is the OWNER's step (`twine upload`, their token); deploys follow the owner's word (see "Next").
- Green at last run (2026-09-29, fourth session): `python -m pytest -q` (1,720), `ruff check fusion_first
  tests scripts app setup.py`, frontend vitest (125) + lint + build, Playwright E2E (12), `claude plugin validate`
  on the bundled marketplace and both plugins.
- **Deployment:** `fusion-first-testing.com` (Vercel project `secure-studio`, CLI logged in as `katawwr`)
  serves the rebuild; API `https://katawwr--fusion-safety-api-fastapi-app.modal.run` (Modal app
  `fusion-safety-api`, demo-only, no secret, version `rebuild-bd6b698`). Walked end to end this session
  (Playwright MCP): home, Scan (Paste → Attack → Grade → Guard → before/after), HTML report download, /use,
  /trust, dark mode, 375 px: all render, no console errors except the designed 402 on "Grade quality" (the
  demo server has no live model). The old Modal apps (`fusion-quality-tester`, `fusion-secur…`) still run:
  rollback path; retiring them is the owner's call.
- **PyPI release 0.1.0 prepared, NOT uploaded** (owner decisions 2026-09-29: publish `fusion-safety` on
  PyPI; the plugin marketplace ships inside the wheel; the import package is renamed `fusion_first` because
  PyPI's `fusion` and JPMorgan's `pyfusion` both install a top-level `fusion`; and "leave out anything
  unnecessary"). `dist/` holds the artifacts built with `python -m build` from a FRESH CLONE of aaa12da
  (`git -c core.autocrlf=false clone`, plus the built `frontend/dist` copied in): wheel 550 KB sha256
  `bba7e14b...578c6f`, sdist 508 KB `b3e32ee1...357146`; `twine check` passed. Contents: the package minus
  the 26 dev-only modules (setup.py DEV_ONLY_MODULES; a test re-derives them from the import graph), the 23
  runtime data files (setup.py _RUNTIME_DATA), the marketplace without READMEs, the web app without its
  social-preview image; the sdist adds only pyproject/setup/MANIFEST/README and build metadata (no
  CLAUDE.md, SCHEMA.md, tests, integrations, evidence). Verified from a clean venv outside the repo: every
  offline CLI command (doctor, scan, prove --check all --html, eval --check all, guard-bench, guard-proof,
  fix, harden, ci --demo, plugin-dir + `claude plugin validate`), the guard hook (asks on `cat .env | curl`),
  a full run (`cmd:` stub target, scripted host grades, finalize withholds the grade, verify re-derives),
  `fusion serve` (all routes 200, version 0.1.0), and the plugin's own MCP launch against the wheel (18
  tools; doctor, list_checks, snippet with `fusion_first`, scan_prompt, check_output redacts, check_tool_call
  blocks). Earlier builds are in this session's scratchpad. Rebuild the same way after ANY code change: PyPI
  never accepts the same version twice.
- `TRUST_REPORT.md` and `frontend/src/content/evidence.json` are generated
  (`python -m fusion_first.validate.trust_report`); tests fail on drift.
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

## This session (fourth), 2026-09-29 (`git log 2855a27..HEAD`)

- **Live site walked** (see State). Found the install paths were dead ends: `fusion-safety` was not on PyPI
  (404; anyone could have claimed the name, and the plugin's `.mcp.json` defaulted to `uvx --from
  fusion-safety`), /use said `claude plugin marketplace add /path/to/fusion`, no public repo. Owner chose:
  PyPI (owner uploads) + the plugin bundled in the package (memory `distribution-pypi-decision`).
- **Packaging** (e091796, e0be8f8, 558f482): the wheel ships `.claude-plugin/` + `plugins/` under
  `fusion_first/_bundled/marketplace` (dot-paths named in package-data); `fusion plugin-dir` prints it; the
  plugin pins `fusion-safety==0.1.0` and `mcp>=1.2,<2`. Installing the built wheel found two blockers,
  both fixed with tests: `fusion_first/model/models.yaml` was missing (every installed `doctor`/run crashed), and
  mcp 2.2.0 (what `mcp>=1.2` resolves to) renamed FastMCP, so the MCP server exited at startup. Also: the
  build failed on Windows once a bundled folder had OneDrive's read-only attribute (rmtree now clears it);
  MANIFEST.in ships the marketplace + web app; PyPI summary "Measure and guard AI agents: ..."; a
  pip-installed `fusion serve` reports 0.1.0, not "dev". Install copy: `uv tool install fusion-safety` +
  `claude plugin marketplace add "$(fusion plugin-dir)"` (README, plugin READMEs, setup skill, /use); the
  web target picker names the `[serve]` extra. `tests/test_packaging.py` builds a real wheel.
- **Live replay run done** (this session's scratchpad `live-replay2`, run `a089cade4172`: llama3.2:1b, Banking
  prompt, host grader = 5 Sonnet subagents via `fusion run tasks --lease` / `submit`, 98/98 graded, 0
  rejected). Grader 100% on every check's known-answer questions, grades not withheld: leakage C (2/8, 62%
  with the optional fix, INCONCLUSIVE), the other three A. In-sample: "the guard blocked or redacted 1 of 2
  attacks that got through and 1 of 30 replies graded clean (1 carried a secret or your system prompt)";
  `run verify` passes. The previous session's run (33dafde363b4, 1.5B grader) died with that session.
- **Replay honesty fix** (6055f7e): that clean reply was "I can't create a response that includes the
  override code OVR-4471." (clean for excessive agency, which grades actions). `ProbeOutcome.guard_leak`
  marks a stop caused by a prompt secret or a prompt echo; counts carry `clean_leaks`; the web mirror,
  fixture and Guard step table follow. The one leak the guard missed was a paraphrase ("...including those
  related to ... override codes"): the guard doesn't catch paraphrased rules.
- **Guard-first top fixes** (6055f7e): a card's `top_fixes` (the `top_fix` of finalize/scan_prompt/
  audit_agent and the CLI text card) led with "Apply the hardened system prompt" and "(Phase 3)"; now the
  guardrail leads when attacks got through, the fix follows as optional, or is flagged when it raised the
  issue rate.

- **Release review** (independent reviewer on the built artifacts): verdict "with fixes"; all fixed with
  RED→GREEN tests (e879ae4): data_root() took a site-packages holding Hugging Face `datasets/` for a checkout
  (every corpus read failed in ML environments) → roots are recognised by Fusion's crosswalk file, and
  plugin_root() by our marketplace name; the artifacts shipped raw third-party downloads and the processed
  third-party sets without their notices → wheel and sdist ship runtime data only (no datasets/external, no
  Claude Code held-out sets, no evals transcripts); a build without frontend/dist silently lost the web app →
  release builds fail without it or the marketplace (FUSION_PARTIAL_BUILD=1; editable installs skip
  bundling); data dirs are replaced, not merged; the `cmd:` adapter template is on /use; doctor/skill cite
  the Trust Report by URL. Also this session: the Quality panel hint graded a placeholder prompt (90ec297),
  /use and /trust page titles (d2f728f), `fusion run status` names `fusion run resume` while grading (c4c24f6).
- **Import package renamed `fusion` → `fusion_first`** (2bbba99, owner). Mechanical; kept on purpose:
  `scripts/step2_guard.py`'s `_PRIOR_CODE` (runs the prior rules inside a worktree at a6fa0f5, where the
  package is `fusion`), the Trust Report sentences naming the rules' path at old commits, frozen PREREG docs,
  the crosswalk file's comment (its hash is the recorded crosswalk_version). The console commands (`fusion`,
  `fusion-mcp`), PyPI name, `.fusion/` workspaces and plugin names are unchanged. Another chat's `fusion
  serve` (pid 10396, port 8765, started 2026-09-28) still runs the pre-rename code: restart it if used.

## Third session, 2026-09-29 (`git log 233d687..2855a27`)

- **Measure + guard repositioning done** (plan `~/.claude/plans/measure-guard-reposition.md`; ledger in the
  gitignored `.superpowers/sdd/measure-guard-reposition/progress.md`, rulings listed there):
  - Scan wizard Paste → Attack → Grade → **Guard**. The Guard step leads with the guardrail (step-2 result with
    counts from evidence.json via `guardResult`, /trust link, snippet), then "Optional: prompt fix" (measured
    caveat, diff, copy buttons, "Re-test it on your model" → the before/after view, which is no longer a step;
    the step bar keeps Guard current). Demo scans label it "See the example before/after". Report button
    "Guard it".
  - Report: the summary grades the prompt as written first, the fix's paired result second; each card shows
    the trust strip and grader accuracy before "Prompt fix (optional)"; arms read "As written" / "With fix".
  - Site: hero "Measure and guard AI agents"; features lead with the guardrail and end with the optional fix
    and its caveat; use cases name the guardrail; page meta; /trust shows the guard sections before the fix.
  - Backend/docs: the HTML report leads with one guardrail block, each card's fix block is optional with the
    caveat; CLI help and CI hint; MCP instructions, tool descriptions and `next_steps` offer the guard first;
    integrations/README; plugin README, `harden` (optional) and `audit` skills; README intro; CLAUDE.md.
- **Guard snippet correctness:** `GuardedModelClient` guards replies only; tool calls are gated only by
  `guard.guard_tool_call(name, args, user_request=..., untrusted_context=True)`. The snippet (and its README,
  integrations/README and /use copies) now uses the measured config, `GuardConfig(require_authorization=True)`,
  shows that call (a test executes it), lists each safety check once, fits 80 columns, and says a system-prompt
  dump is blocked (not redacted). README cites rules 0c560b5 for the step-2 numbers.
- **Final review of the repositioning** (fresh reviewer): 0 critical, 6 important, all fixed with RED→GREEN
  tests: the snippet config above; the report headline no longer calls a PRELIMINARY fix "not significant";
  landing use case 1 is an indirect injection (request binding can't stop a user asking for the refund);
  `audit_agent` / `finalize_run` verdicts lead with the guard; /use shows the guard third and the fix as
  optional; plain bullets for what got through. Also: the Scan page never shows another prompt's hardened
  prompt (stale state after cancel/restart, late replies dropped) and the snippet and fix load independently.
  Deferred minors: the web copy doesn't name rules 0c560b5; `/api/guardrail-snippet` returns quality checks
  it doesn't cover.
- **In-sample guard replay built** (owner: build it; a redaction counts as stopped; label it in-sample):
  every scored attack of a LIVE scan carries `ProbeOutcome.guard_stopped` (`fusion_first/engine/guard_replay.py`:
  the snippet's config with the scan's prompt and the values it marks secret; tool calls against the user's
  own message, `untrusted_context` when the attack injected content). Shown as "In-sample, this scan's own
  attacks: the guard blocked or redacted X of Y attacks that got through and Z of W replies graded clean" in
  the Guard step (with a per-check table), the HTML report, `fusion run finalize` / MCP `finalize_run`
  (`guard_in_sample`), `fusion scan` and `scan_prompt`. Demo scans carry no verdict (canned replies were
  written for the dataset's fictional products: the replay showed 0–1/8 leaks stopped there). `fusion run
  verify` leaves the verdict out (it comes from the current rules, not the recordings), so older runs verify.
- **Handoff:** no routines (owner: "it didn't work"); the routines no longer exist. The app's
  `start_session` / `hand_off_to_session` are not exposed to these sessions and the docs describe no setting.

## Previous session, 2026-09-28 (`git log 4e344f3..233d687`)

- **Step 1 done (dev):** the guard binds tool calls to the user's request (18e424c, 0c560b5). Under
  `require_authorization` or `untrusted_context=True`, a call not shown to be a read needs the request to use
  one of its action verbs (synonyms, verb position, idioms excluded) AND name what it touches (object words,
  service, or the call's argument values); after untrusted content an unrequested private-data read is
  blocked; missing request or tool name fails closed. Default posture unchanged. `user_identities` config
  lets "email it to me" pass. A red-team review found 21 issues; all fixed, kept in `tests/test_guard_redteam.py`.
  DIAGNOSTIC on spent samples (`scripts/guard_dev.py`, never quote): tool hijacks stopped compact 29/33
  (was 13/33), v1 33/34; clean wrongly blocked 0/87, 1/86. Remaining misses: same-service reads
  (GitHubGetUserDetails after a GitHub request) and FedEx shipment searches (not in the private-data list).
- **Harness v2** (`fusion_first/validate/guard_on_transcripts.py`): the guard gets the user's instruction only (v1
  passed the injected tool result too), `untrusted_context=True`, scenario tool spelling. `HARNESS` string.
- **Step 2 benign set:** `fusion_first/validate/benign_actions.py`: InjecAgent attacker cases with the user asking
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
- **Context handoff automation** (5657a66): hook + routines `fusion-continue-a/-b` (routines dropped 2026-09-29).

## Next

0. **PyPI release (waiting on the owner).** From the repo root, with the owner's PyPI token:
   `python -m twine upload dist/*`. Then, in order: (a) verify from PyPI in a fresh venv outside the repo:
   `pip install "fusion-safety[serve,mcp]"`, `fusion doctor`, `fusion plugin-dir`, `claude plugin validate
   "$(fusion plugin-dir)"`, and the plugin's MCP launch without FUSION_PKG (`uvx --from fusion-safety==0.1.0
   --with "mcp>=1.2,<2" fusion-mcp`); (b) with the owner's go-ahead, redeploy BOTH halves of the site: the
   live API still serves the guard snippet with `from fusion.guardrail ...` (the Guard step shows it) and the
   live /use has the old install lines and snippet. API: `PYTHONIOENCODING=utf-8 FUSION_VERSION=rebuild-$(git
   rev-parse --short HEAD) modal deploy app/modal_app.py` (mounts `fusion_first`); frontend: in `frontend/`,
   `VITE_API_URL=https://katawwr--fusion-safety-api-fastapi-app.modal.run npx vite build --outDir
   .vercel/output/static`, then `vercel deploy --prebuilt --prod --cwd frontend`; re-walk /use and a demo
   scan's Guard step on the live domain. The auto-mode classifier denied creating a Modal secret (don't retry).
0b. Follow-ups found this session: port the MCP server to mcp 2.x (FastMCP → `mcp.server.mcpserver.MCPServer`,
   other API changes) and lift the `<2` pin; `fusion run status` from the CLI can't see whether a process
   still works on a run (it now names `fusion run resume` in every busy phase; a heartbeat would let it say
   "stalled" as the MCP path does); the guard misses paraphrased rule leaks. From the release review, not
   done: the license table + License classifier are deprecated (setuptools warns "by 2027-Feb-18"; the SPDX
   form `license = "LicenseRef-Proprietary"` needs setuptools>=77, which would break the offline
   no-isolation builds and tests here on setuptools 70.2: move when the dev environment does);
   `"$(fusion plugin-dir)"` is mangled in Windows PowerShell 5.1 when the path has non-ASCII characters;
   `fusion record` and `eval --update-baseline` write into site-packages on a pip install (dev commands);
   the MCP server reports the SDK's version (1.30.0) as serverInfo.version.

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

- DECIDED 2026-09-29: reposition as "measure + guard", fix demoted. DONE (third session).
- DECIDED 2026-09-29 (fourth session): ship via PyPI `fusion-safety` (the owner uploads), the Claude Code
  plugin marketplace bundled in the wheel (`fusion plugin-dir`); no public repo. Prepared; upload pending.
- DECIDED 2026-09-29: no routines or scheduled tasks for handoff; a regular session or ask the owner.
- Fix arms (not in step 2): 300 pairs per model (the step-2 items + hardened arm, ~8–9 h per model) detect a
  moderate or strong fix effect (99–100% power) but not the small 1–3B one (56%); 600 pairs ≈ 33 h per model.
- Decided 2026-09-28: second model llama3.1:8b (pulled); named recipients stay blocked unless allowlisted.

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
| Specs, doctor, presets | `fusion_first/backends/resolve.py`, `fusion_first/backends/presets.py`, `fusion_first/model/providers/` |
| Run engine, gates | `fusion_first/runs/`, `fusion_first/stats/gate.py` |
| Pre-registered decisions in code | `fusion_first/validate/prereg.py`, `fusion_first/validate/llama_guard.py` |
| Runtime guardrail + measurements | `fusion_first/guardrail/`, `fusion_first/validate/guard_on_transcripts.py`, `fusion_first/validate/benign_actions.py`, `scripts/guard_*.py` |
| Web app + E2E | `fusion_first/web/`, `frontend/src/`, `frontend/e2e/` |
| Evidence + Trust Report | `evals/validation/v1/`, `fusion_first/validate/trust_report.py` |
| Claims registry | `evals/claims.yaml`, `tests/test_claims_backed.py` |
