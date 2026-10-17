# Changelog

All notable changes to `fusion-safety`. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.1] - Unreleased

### Added

- Guard: `Guardrail.guard_tool_call(..., untrusted_text=...)` and the MCP tool `check_tool_call(untrusted_text=...)`.
  Given the tool results so far, a read they ask for alongside a send to an outside address is blocked. This is
  pre-registered step 3, adopted; the guardrail snippet now passes the tool results.
- Model layer: native tool calls. `ModelRequest.tools` offers function schemas and `ModelResponse.tool_calls`
  returns the calls (Ollama and OpenAI-compatible providers); cassettes record and replay them. Requests without
  tools keep their cassette keys.
- A registered study of a tool-result injection detector, sealed before scoring:
  [Trust Report Q5](TRUST_REPORT.md#q5-does-a-trained-detector-beat-the-phrase-list-on-injected-tool-results) and
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
