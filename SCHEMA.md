# Canonical schema (frozen)

The single source of truth is `fusion_first/schemas.py`. This document explains it; the code is
authoritative. Freezing these names resolved the cross-lens naming conflicts from design: every
module imports these types and none redefine them.

## Agent trajectory (the unit a scan targets)

An agent interaction is a `Trajectory` = ordered `Step`s. This is the agentic core: a target is a
trajectory, not just a prompt string.

- `Step(role, content, tool_call?, tool_result?, thinking?)`: `role ∈ {system,user,assistant,tool}`.
- `ToolResult(tool, content, injected)`: **`injected`** marks untrusted/attacker-controlled
  content (the indirect-injection surface). It lives on the tool result, not the step.
- Field name is **`content`** everywhere (never `text`).
- Helpers: `system_prompt()`, `final_response()`, `has_injection()`, `transcript()`.

## Labels vs Verdicts (kept distinct on purpose)

- `Label(is_issue, severity, issue_type, source)`: **ground truth** from a deterministic oracle or
  a user-supplied labeled example. `source` e.g. `"oracle:injecagent"`.
- `Verdict(is_issue, severity, issue_type, criteria[], rationale, confidence, judge_model)`: the
  **judge's** decision. Derived deterministically from the binary `CriterionVerdict`s.

Bar A compares `Verdict.is_issue` (judge) against `Label.is_issue` (oracle). We never conflate them.

## Rubric

- `Rubric(check, intent, criteria[], owasp)` where `Criterion(id, question, weight_severity)` is a
  binary yes/no question ("yes" = issue present). The judge answers each with evidence; the overall
  verdict is a function of the criteria (auditable). OWASP codes come from the crosswalk YAML.

## Proof result types

- `Interval(point, low, high)`: every rate carries one (Wilson CI or bootstrap CI).
- `AccuracyResult`: Bar A: precision/recall/F1/accuracy (+CIs), Cohen's kappa, confusion counts.
- `BeforeAfterResult`: Bar B: baseline/hardened issue rates, absolute reduction (CI), McNemar p,
  discordant counts, and an `Honesty` badge (`PROVEN | PRELIMINARY | INCONCLUSIVE`).
- `BenchmarkResult`: Bar D: detector TPR/FPR on a public-benchmark subset.
- `SafetyReportCard`: fuses the bars, a letter `grade`, OWASP tags, top fixes, provenance hashes
  (`gold_version`, `crosswalk_version`, `judge_model`, `verification_hash`), and a `demonstration`
  flag (True when built from the offline stand-in judge: never a real efficacy claim).
- `ScanResult`: a user-prompt scan: its cards plus one `ProbeOutcome` per attack (`baseline_issue` /
  `hardened_issue`, None = unscored). `ProbeOutcome.guard_replay` is the in-sample guard replay on that
  prompt-as-written reply (`fusion_first/engine/guard_replay.py`): `stopped` (the snippet-configured guard
  blocked or redacted something), `allowed`, or `no_tool_call` (a tool-action attack answered in prose:
  nothing for the tool-call check to see). `guard_leak` marks a stop because the reply carried a value
  the prompt marks secret, or the prompt itself: a catch even when the attack's own check graded the
  reply clean. Both come from the current guard rules, not the recordings, so `fusion run verify`
  leaves them out; None = not evaluated (unscored, quality, demo).

## Persistence

There is no database: no accounts, credits or billing. Web scans live in a process-local store
(`fusion_first/web/persistence.py`), runs in the local run store (`.fusion/runs/`), and the gold set,
probes and cassettes are **jsonl/JSON in git**.
