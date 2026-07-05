# Fusion First — project guide for Claude

Fusion First is an **offline "test + prove" engine for agentic AI safety**. You connect an agent
(or paste a prompt), Fusion builds an OWASP-mapped attack suite, runs **baseline vs hardened**, and
returns a **Safety Report Card** where every number carries a confidence interval or an honesty
badge. The wedge is *proof*: a calibrated, cross-family, rubric-decomposed judge measured against
ground truth. Brand ("Fusion First"), `frontend/public/logo.png`, and the purple/cyan/pink
`fusion` palette are fixed and must be preserved.

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
  - `judge/` — rubric-decomposed binary-criteria judge (the accuracy fix).
  - `stats/` — `metrics.py` (Bar A: Wilson CI, kappa), `paired.py` (Bar B: McNemar, bootstrap,
    honesty badge), `calibration.py` (judge-vs-oracle harness), `gate.py` (the regression gate).
  - `attacks/taxonomy.py` — resolves OWASP codes from `crosswalk/owasp_crosswalk.v2025.yaml`.
  - `engine/` — `before_after.py` (Bar B runner), `report.py` + `report_html.py` (Safety Report
    Card, clean theme-aware HTML), `fixes.py` (automated remedies / `harden`).
  - `guardrail/` — the RUNTIME safety layer: `guard.py` (input fence / output redact-block /
    tool-call policy), `policy.py` (GuardConfig), `client.py` (GuardedModelClient), `simulate.py`
    (replays attacks through the guard to prove issue-rate reduction).
  - `goldset.py`, `recording.py` — load gold/probes; record demo cassettes.
- `app/` — thin Modal + FastAPI wrappers (the only place `modal` may appear). WIP.
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
```

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
