# Fusion First — project guide for Claude

Fusion First is a **proof-grade evaluation engine for AI agents — safety AND quality**. You connect
an agent (or paste a prompt), Fusion tests it and returns a **Report Card** where every number carries
a confidence interval or an honesty badge. The wedge is *proof*: a cross-family judge whose accuracy
is measured against ground truth in every run, with grades withheld when it can't be trusted (no
vibes-based metrics). The rubric makes a grade checkable (per-criterion answers, quoted evidence); it
is NOT shown to be more accurate than a plain one-question judge (pre-registered B3, Trust Report Q4),
so never claim it is. Two dimensions run
through the identical judge: **safety** (OWASP-mapped adversarial attacks — injection, excessive
agency, exfiltration, prompt leakage; `kind="safety"`) and **quality** (correctness / instruction
following; `kind="quality"`). Product focus is **open-weight / less-robust models** (Ollama target,
judged by Claude cross-family): frontier models resist most safety attacks, open-weight models often
don't. **Numbers come only from committed evidence** (`evals/claims.yaml`, enforced by
`tests/test_claims_backed.py`) — never from memory or unrecorded runs. Brand ("Fusion First"),
`frontend/public/logo.png`, and the purple/cyan/pink `fusion` palette are fixed and must be preserved.

## The one rule that matters most

**Nothing under `fusion/` may import `modal`.** The pure core must stay runnable offline under
plain `pytest`/`uvicorn`. Modal/FastAPI wrappers live in `app/`. Enforced by
`tests/test_no_modal_import.py` — do not defeat it.

## Layout

- `fusion/` — pure core (no `modal`):
  - `schemas.py` — the canonical data model (Trajectory/Step/ToolResult, Label vs Verdict, proof
    result types). Every module imports these; none redefine them. See `SCHEMA.md`.
  - `model/` — provider-agnostic `ModelClient`, `registry.py` (roles + allowlist + self-family
    guard), `replay.py` (cassette record/replay for deterministic offline runs), `providers/`.
  - `judge/` — rubric-decomposed binary-criteria judge (per-criterion answers + quoted evidence, which
    the run engine checks; no more accurate than a plain question with Sonnet — see Trust Report Q4).
  - `stats/` — `metrics.py` (Bar A: Wilson CI, kappa), `paired.py` (Bar B: McNemar, bootstrap,
    honesty badge), `calibration.py` (judge-vs-oracle harness), `gate.py` (the regression gate).
  - `attacks/taxonomy.py` — resolves OWASP codes from `crosswalk/owasp_crosswalk.v2025.yaml`.
  - `engine/` — `before_after.py` (Bar B runner), `report.py` + `report_html.py` (Safety Report
    Card, clean theme-aware HTML), `fixes.py` (automated remedies / `harden`).
  - `guardrail/` — the RUNTIME safety layer: `guard.py` (input fence / output redact-block /
    tool-call policy), `policy.py` (GuardConfig), `client.py` (GuardedModelClient), `simulate.py`
    (replays attacks through the guard to prove issue-rate reduction).
  - `goldset.py`, `recording.py` — load gold/probes; record demo cassettes.
  - `runs/` — the keyless run engine: `engine.py` (collect -> grade -> strict-replay finalize ->
    verify; grade WITHHELD ('?') unless every question is answered, the grader clears the policy
    floor on blind known-answer questions AND agrees with `oracle_check.py` on the run's own
    clear-cut transcripts), `logs.py` (grade existing transcripts), `service.py` (shared by CLI +
    MCP; resume, stalled-run detection), `cli.py`.
  - `backends/resolve.py` — target/grader spec strings (`ollama:<m>`, `claude-cli:<m>`, `host`,
    `ollama-prob:<m>`) -> budgeted clients; `doctor()`. Never selects a metered path.
  - `validate/` — oracles, IFEval-lite, baselines, importers, evidence experiments, claims registry,
    `judge_eval.py` (grader vs deterministic oracles on real transcripts), `trust_report.py`
    (GENERATES `TRUST_REPORT.md` + `frontend/src/content/evidence.json` from `evals/`; a test
    fails if they drift — regenerate with `python -m fusion.validate.trust_report`).
  - `integrations/` — `mcp_server.py` + `run_tools.py` (MCP v2), `agent_tools.py` (one-shot tools),
    `claude_hooks.py` (fusion-guard PreToolUse/PostToolUse), `live.py`.
- `plugins/fusion/` — Claude Code plugin (skills audit/grade/harden/setup/guard, `fusion-judge`
  agent limited to the grading tools); `plugins/fusion-guard/` — opt-in hooks. Marketplace:
  `.claude-plugin/marketplace.json`. `tests/test_plugin.py` pins tool names against the server.
  - `web/` — the pure FastAPI layer (`factory.py`, SSE, settings) and `serve.py` (`fusion serve`).
- `app/` — the Modal wrapper (`modal_app.py`, the only place `modal` may appear) plus alias shims
  re-exporting `fusion/web`.
- `backend/main.py` — the legacy 6,664-line monolith being decomposed. Do not add features here.
- `datasets/gold/`, `datasets/probes/` — jsonl gold set + paired probes (diffable, in git).
- `cassettes/` — committed deterministic model responses keyed by request hash.
- `crosswalk/` — pinned OWASP LLM 2025 + Agentic 2026 crosswalk.
- `evals/` — committed accuracy baselines the gate compares against.
- `scripts/fusion_cli.py` — `record` | `eval` | `prove`. `scripts/hooks/` — the gate hooks.

## Commands

```bash
python -m pytest -q                      # full offline suite (must stay green)
python -m pytest -m unit -q              # fast unit subset
python -m ruff check fusion tests scripts
python scripts/fusion_cli.py record --check all      # rebuild demo cassettes (all 4 checks)
python scripts/fusion_cli.py eval   --check all      # run the accuracy gate for every check
python scripts/fusion_cli.py eval   --check direct_prompt_injection --update-baseline
python scripts/fusion_cli.py prove  --check all --html report.html   # Safety Report Card(s) + HTML
python scripts/fusion_cli.py fix    --check excessive_agency         # print the guardrail block
python scripts/fusion_cli.py harden --prompt my_prompt.txt --write   # AUTO-APPLY the fix in place
python scripts/fusion_cli.py guard-proof --check all                 # runtime guardrail reduction
python -m fusion.cli doctor                                          # keyless backends (no model calls)
python -m fusion.cli run start --prompt p.txt --target ollama:llama3.2:1b --grader ollama-prob:qwen2.5:7b
python -m fusion.cli run finalize && python -m fusion.cli run verify # card + offline re-derivation
python scripts/run_evidence.py run|analyze --n 30                    # oracle-labelled evidence (local)
python scripts/judge_eval.py prepare|grade|score --workspace W --run-id R   # grader vs oracle (Q1)
python -m fusion.cli run logs --file logs.jsonl --check everything   # grade existing transcripts
python -m fusion.cli import-promptfoo results.json                   # honest stats on promptfoo output
python -m fusion.validate.trust_report                               # regenerate TRUST_REPORT.md
claude plugin validate plugins/fusion                                # plugin manifest check
python -m fusion.cli serve                                           # local web app, 127.0.0.1:8765
npm --prefix frontend run build && python -m pip wheel . --no-deps --no-build-isolation -w dist  # wheel bundles corpora + frontend/dist
```

`fusion serve` (`fusion/web/serve.py`) has three locks, each pinned by `tests/test_serve.py`: loopback
bind, Host allowlist (DNS rebinding), and a per-launch token injected into the served page and
required on every non-GET `/api/` call. A page it serves always calls its own origin
(`frontend/src/lib/scanApi.js`), whatever `VITE_API_URL` the build baked in.

Checks: `direct_prompt_injection`, `excessive_agency`, `data_exfiltration`, `system_prompt_leakage`
(use `--check all` to run every one). Each ships a remedy in `fusion/engine/fixes.py`; `harden`
appends idempotent guardrails to a system prompt. The branded, theme-aware HTML card lives in
`fusion/engine/report_html.py` (no gradient; clean/professional; copy-paste fix block).

## How "proof" works (and stays honest)

- **Bar A** — judge vs a labeled gold set (precision/recall/F1/kappa with Wilson CIs), reported on
  the held-out `blind` split.
- **Bar B** — paired before/after (McNemar exact + bootstrap CI) with a **PROVEN / PRELIMINARY /
  INCONCLUSIVE** badge that refuses to overclaim on small samples.
- **Bar C** — every check maps to OWASP LLM 2025 + Agentic 2026 codes (crosswalk YAML). The ASI
  codes are provisional until re-verified against the published doc (WebFetch) — see the YAML note.
- Offline, the LLM judge is a deterministic **heuristic stand-in** so the whole loop runs without
  keys; any card built that way is stamped `demonstration=True`. Supplying a real Claude key and
  re-recording cassettes yields real numbers with **no other change** to the harness.

## Workflow expectations

- TDD: add/extend a test with every change; keep `pytest -q` green before moving on.
- The **Stop hook** runs unit tests + the eval gate (advisory). The **PreToolUse hook** blocks
  `modal deploy` if the accuracy gate is red. The **PostToolUse hook** lints edited Python.
- Model IDs live only in `fusion/model/models.yaml`; reference models by **role**, never hardcode
  IDs in logic. Default judge role → `claude-sonnet-5`; calibration/escalation → `claude-opus-4-8`.
- Security posture is load-bearing: keys server-side only, per-user budgets/allowlist, fail-closed
  webhooks. Never reintroduce the deleted `/api/debug/*` endpoints or `modal.Dict` money state.
- **Zero spend.** Real model calls go only through the `claude` CLI on subscription auth or local
  Ollama. Never set API keys; never run `claude auth login|logout|setup-token` (not even `--help`) —
  they can change the CLI's login and are denied in `.claude/settings.json`. `claude auth status` is
  fine. Never run `pytest -m live` against the CLI without the user's go-ahead.
