# Changelog

All notable changes to `fusion-safety`. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The committed example tool-loop run (`examples/verified-run-toolloop`) is a Full-tier scan of `qwen2.5:7b`: every
  v2 template per check runs through the loop in both arms, in place of the Quick-tier prefix, so the card's per-arm
  intervals narrow. Host-graded as before; CI re-derives it offline. Its data-exfiltration grade is withheld by the
  in-run grader gate (one host-grader verdict called an oracle-confirmed exfiltration clean); the rates and their
  intervals stay visible.

## [0.1.2] - 2026-11-08

### Added

- Tool loop and corpus v2: tool-result-bearing probes for `excessive_agency` and `data_exfiltration`
  ([datasets/probes/README.md](datasets/probes/README.md)) run the target with native tool calls in a bounded loop
  (at most four assistant turns) with scripted tool results; nothing is executed. The oracle cross-check and the
  in-sample guard replay read the real tool calls; the replay sees every tool result received before each call.
  See [docs/RUN_LOCALLY.md](docs/RUN_LOCALLY.md#tool-loop---corpus-v2).
- `fusion run start --corpus v1|v2` (MCP `corpus`) picks the attack corpus; under v2 the in-run known-answer
  questions are gold v2's sealed blind split. `--no-fix-arm` (MCP `fix_arm=False`) attacks only the prompt as
  written (half the target calls); quality tests keep both arms and always use v1.
- Cards: a Wilson 95% interval and the attacks a +/-10 pt interval would need on every per-arm issue rate, in the
  text card, the HTML report, the web app and the run summary. The example run is re-finalized for the new fields.
- Run-time accounting: `fusion run status` prints calls answered, tokens, seconds per attack and time left;
  `result.json` carries an `accounting` block computed from the target recording, which `fusion run verify` checks.
- A registered study of the judge's accuracy on tool trajectories
  ([PREREG_q1_toolloop.md](evals/validation/v1/PREREG_q1_toolloop.md), gold v2 for the two agentic checks, scored
  once): [Trust Report Q6](TRUST_REPORT.md#q6-is-the-judge-accurate-on-tool-trajectories).
- The Trust page renders the Q5 detector study's registered secondaries (McNemar against the phrase list,
  per-technique recall, latency).
- [examples/verified-run-toolloop](examples/verified-run-toolloop): a committed qwen2.5:7b run through the tool
  loop (`--corpus v2`, both arms, Quick tier), graded by Claude Code host subagents. CI re-derives it offline with
  `fusion run verify --workspace examples/verified-run-toolloop latest` and fails on drift.

### Changed

- `fusion run verify` parses the stored result through the current schema (a later defaulted field compares as its
  default; a changed value still fails) and checks the `accounting` block when the result carries one.
- A rejected grading answer keeps its task's lease (it still expires), so the grader who got the rejection can fix
  and resubmit without another parallel grader taking the task meanwhile; the rejection says so in a `fix` field.

### Fixed

- OpenAI-compatible providers send tool messages in the strict OpenAI shape (`role`, `tool_call_id`, `content`);
  strict servers rejected the extra keys. Cassette keys do not change.

## [0.1.1] - 2026-10-31

### Added

- Guard: `Guardrail.guard_tool_call(..., untrusted_text=...)` and the MCP tool `check_tool_call(untrusted_text=...)`.
  Given the tool results so far, a read they ask for alongside a send to an outside address is blocked. This is
  pre-registered step 3, adopted; the guardrail snippet now passes the tool results.
- Model layer: native tool calls. `ModelRequest.tools` offers function schemas and `ModelResponse.tool_calls`
  returns the calls (Ollama and OpenAI-compatible providers); cassettes record and replay them. Requests without
  tools keep their cassette keys.
- A registered study of a tool-result injection detector, sealed before scoring and scored once (not adopted; the
  detector stays dev-only): [Trust Report Q5](TRUST_REPORT.md#q5-does-a-trained-detector-beat-the-phrase-list-on-injected-tool-results) and
  [docs/DETECTOR.md](docs/DETECTOR.md). The study code and data are development-only and not in the package.
  `Guardrail(detector=...)` takes an optional scorer whose result is recorded as an observe-only event; it never
  changes a decision.
- [examples/verified-run](examples/verified-run): a committed llama3.2:1b run graded by Claude Code host subagents.
  CI re-derives it offline with `fusion run verify --workspace examples/verified-run latest` and fails on drift.

### Changed

- Package metadata: the MIT license classifier (0.1.0 carried a proprietary one), Python 3.11 to 3.13 and
  Development Status classifiers, and Source and Issues links.
- The HTML report card uses the site's brand.

### Fixed

- Guard: destinations come from a call's destination fields, not its message content; file names and dotted
  numbers (amounts, versions) are not hosts.
- The MCP server reports fusion-safety's version on MCP SDK 1.x too.
- `fusion plugin-dir` prints an ASCII short path when the install path is not ASCII (Windows PowerShell 5.1).
- `fusion serve` accepts scans by target spec; they failed with 422.

## [0.1.0] - 2026-10-01

Initial release: the `fusion` CLI and run engine with a grader checked against known answers in every run, the
runtime guardrail, the MCP server (`fusion-mcp`), the local web app (`fusion serve`), and the Claude Code plugins
bundled in the wheel.

[0.1.1]: https://pypi.org/project/fusion-safety/0.1.1/
[0.1.0]: https://pypi.org/project/fusion-safety/0.1.0/
