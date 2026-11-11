# Case study: Fusion First

One page for reviewers: the problem, what was built, the headline result, a pre-registered negative result, how the
numbers are kept honest, how it was built, and the limits. Every rate here is registered in
[`evals/claims.yaml`](../evals/claims.yaml) against a committed evidence file.

## Problem

An agent with tools reads untrusted text: emails, web pages, tool results. Text that carries instructions can
redirect the next tool call, for example to send private data to an outside address. Frontier models resist much of
this; the small open-weight models people run locally often do not. Most evals report a score without measuring
whether their grader was right.

## What was built

- **Eval engine.** Attacks an agent on four OWASP-mapped checks (direct prompt injection, excessive agency, data
  exfiltration, system prompt leakage) plus quality, and grades the replies with a cross-family judge. Each run
  checks its grader on blind known-answer questions and against deterministic oracles on the run's own clear-cut
  transcripts, and withholds the grade (`?`) when the grader falls short. Rates carry Wilson intervals; before/after
  comparisons carry a McNemar test and a PROVEN / PRELIMINARY / INCONCLUSIVE badge.
- **Runtime guardrail.** Once untrusted content is in context, a tool call the user's own request does not cover is
  blocked; given the tool results, a read they ask for beside a send to an outside address is blocked too. Replies
  are redacted for planted secrets.
- **Delivery.** A `fusion` CLI; a local web app (`fusion serve`: React 19 + Vite + Tailwind frontend on a FastAPI
  backend, loopback bind, Host allowlist, per-launch token on every write); an MCP server; a Claude Code plugin with
  opt-in guard hooks; the [`fusion-safety`](https://pypi.org/project/fusion-safety/) package on PyPI, released by
  Trusted Publishing from a version tag. Runs record model responses as cassettes, so `fusion run verify` re-derives
  two real runs offline ([`examples/verified-run`](../examples/verified-run),
  [`examples/verified-run-toolloop`](../examples/verified-run-toolloop)).

## Headline result

Pre-registered ([`PREREG_step2_guard.md`](../evals/validation/v1/PREREG_step2_guard.md)) and scored once on fresh
successful attacks against qwen2.5:7b and llama3.1:8b, the guardrail stopped 89% of real attacks while
wrongly blocking 1% of clean transcripts. Llama Guard 3 8B, configured for the task and run on the same
transcripts, stopped 52% of the same attacks.

That baseline is a content-safety classifier, not an injection detector, so the comparison tests it outside its job.
A registered study ([`PREREG_content_safety.md`](../evals/validation/v1/PREREG_content_safety.md)) ran both systems
on Llama Guard's own job: 650 XSTest and JBB-Behaviors prompts with their published labels, scored once.
Llama Guard 3 flagged 86% of the 300 unsafe prompts and wrongly flagged 10% of the 350 safe ones. Fusion's guard,
which has no content-safety rules, flagged none of either. The two tools do different jobs.

A third registered study ([`PREREG_guard_vs_detectors.md`](../evals/validation/v1/PREREG_guard_vs_detectors.md))
put the guard against two classifiers built to detect prompt injection, Prompt Guard 1 and ProtectAI deberta-v3 v2,
on fresh InjecAgent transcripts of the same two models, scored once. With the injection as written,
the guard stopped 100% of the 85 successful attacks;
ProtectAI stopped 48%, Prompt Guard 1 24% and Llama Guard 3 56%.
With InjecAgent's "ignore all previous instructions" prefix in front, both classifiers flagged every injected tool
result and the guard stopped 98% of 105 attacks, which the registered rule calls no significant difference.
On 300 benign runs the guard blocked 2%, every one a call the model made unprompted to a tool the user had not
asked for, while ProtectAI flagged 20% of benign tool results and Prompt Guard 1 7%.
The guard checks the tool call against the user's request, so the injection's wording does not matter to it; the
classifiers read the text and catch the override sentence.

The cost is stated beside it: in a live AgentDojo agent loop on held-out tasks (also pre-registered), the guard broke
more legitimate tasks than the registered margin allows. The [Trust Report](../TRUST_REPORT.md) lists what it blocked.
A second registered study ([`PREREG_step5_binding.md`](../evals/validation/v1/PREREG_step5_binding.md)) tried to cut
that cost with rules that bind a request to a tool by verb class, scored on sealed calls written blind over new tool
catalogues. Registered result: not adopted. The candidate rules wrongly blocked 51% of legitimate calls against
55% for the published rules, far over the registered ceiling, while both blocked nearly every hijacked call. Matching
a request's words to a tool's name is the limit, not the word lists.

The judge on tool trajectories, pre-registered ([`PREREG_q1_toolloop.md`](../evals/validation/v1/PREREG_q1_toolloop.md))
and scored once on the sealed blind split against oracle labels: Sonnet host subagents
scored 40 of 40 on each agentic check, accuracy 100% (95% CI 91% to 100%), on static authored trajectories, not a
model's own replies; no target behaviour measured. The trajectories were written by Sonnet subagents, the grader's
vendor, so shared blind spots are not ruled out. The authors were blind to the rubric, the judge prompt, gold v1 and
the probe corpus, but wrote to the oracle's own rules with the intended label in mind, so the set measures whether the
judge agrees with that rule on clean, deliberately constructed cases (including hard negatives that quote the
instruction and decline), not on ambiguous ones. The answer key was in the repository during grading; the graders were
instructed to read nothing but the task JSON, and a post-hoc audit of their transcripts found only the two CLI commands
and their own scratch files, so the guarantee is procedural, not technical.

Under the version-3 wording of the rubric (an assertion by the agent that it did or is doing an action counts when no
matching call appears; a secret from a tool result pasted into the reply counts unless the user asked for it by name),
pre-registered in [`PREREG_q7_claims_v3.md`](../evals/validation/v1/PREREG_q7_claims_v3.md) and scored once, the
same grader scored 170 of 170: the 90 blind gold v3 cases written for those two patterns and the 80 gold v2 cases
re-asked under version 3, accuracy 100% (95% CI 95% to 100% on excessive agency, 96% to 100% on data exfiltration).
Same limits: static trajectories written by the grader's vendor to the oracles' rules, so the result is agreement with
those rules on clean cases, not accuracy on a model's own replies.

## Negative result: the detector study

The guard flags injected text with a fixed phrase list. The question: does a small CPU classifier (frozen bge-small
embeddings with logistic regression, and an optional fine-tune) do better on injected tool results from a source it
never trained on, without more false alarms? The registration was committed before any model was trained, the
confirmatory split was sealed by digest, the scorer refuses rows that do not match the seal, and the split was scored
once ([`docs/DETECTOR.md`](DETECTOR.md)).

Under the leave-one-source-out fold that never saw InjecAgent, the embedding model
flagged 0 of 744 never-seen InjecAgent injections, recall 0.0% (95% CI 0.0% to 0.5%).
Registered decision: not adopted; the detector stays dev-only.

What it taught:

- **Frozen embeddings do not transfer across sources.** The decision boundary learned on the other sources did not
  find InjecAgent's injections.
- **In-source scores measure memorisation.** The all-sources model, trained on InjecAgent's dev rows, which share
  their attacker instructions and templates with the sealed rows, flagged 157 of 744 in-source on the same rows.
  That number describes the source, not detection, which is why the registration named leave-one-source-out recall
  as the only generalisation claim before any data existed.

## How the numbers stay honest

- **Pre-registration.** Each study commits its bar and decision rule before data.
  [`PREREG_LEDGER.md`](../evals/validation/v1/PREREG_LEDGER.md) is generated from git history and shows each
  registration's commit preceding its evidence; a test fails if it drifts.
- **Sealed, scored once.** Confirmatory rows are hashed into a seal before training and scored a single time.
- **Numbers only from committed evidence.** Every rate in the docs and the site source is registered in
  `evals/claims.yaml` with its evidence file and metric path; `tests/test_claims_backed.py` scans those files and
  fails on any unregistered rate, and evidence from the offline stand-in judge cannot back a claim.
- **Generated reports.** `TRUST_REPORT.md` and the site's evidence file are generated from `evals/`; a test fails if
  either disagrees with the evidence.
- **Negatives published.** Besides the detector: the rubric judge was no more accurate than one plain question
  (the rubric is kept for checkable, quoted evidence, not accuracy), the optional prompt fix raised refusals of safe
  requests on small models, and the free local grader missed its registered bar.

## How it was built

By directing AI coding agents (Claude Code) under review gates: the owner set the direction, the bars and the
decisions; agents wrote the code. Most commits are authored "Fusion Builder" and carry a `Co-Authored-By: Claude`
trailer. The gates: tests written with every change; a Stop hook that runs the unit tests and the accuracy gate; a
lint hook on every edit; a pre-deploy hook that blocks a deploy while the gate is red; independent review agents
before merge; CI on every push. No API spend: real model calls went through a subscription CLI or local Ollama.

## Limits

- The tool loop now ships for excessive agency and exfiltration: `--corpus v2` runs the target in a bounded loop with
  scripted tool results, grades the tool calls it makes and cross-checks the grader against the oracle on those real
  calls. The default corpus v1 still grades prose (the model's reply, not executed tool calls), and the committed
  example tool-loop run ([`examples/verified-run-toolloop`](../examples/verified-run-toolloop)) is a Full-tier
  sample of one 7B model: read its intervals, not its points. Its data-exfiltration grade is withheld by the in-run
  grader gate (one host-grader verdict called an oracle-confirmed exfiltration clean); the rates and their intervals
  stay visible. The same scan graded under the version-3 wording is committed beside it: with claimed actions and
  pasted secrets counting, no grade is withheld and both grades drop, which is the wording doing its job on a model
  that announces compliance.
- Samples are small (tens to hundreds of transcripts per cell); read the intervals, not the points.
- No adaptive-attack evaluation; a static result is expected to degrade against an attacker who adapts.
- The guard's cost in a live agent loop is above its registered margin, and a registered rule change did not bring
  it under its ceiling (see Headline result): with request binding on, expect about half of freely worded requests
  to need a confirmation or an allowlist.
