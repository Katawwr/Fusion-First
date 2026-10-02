---
name: audit
description: Audit an AI agent's system prompt with Fusion First, safety (prompt injection, excessive agency, data exfiltration, system-prompt leakage; OWASP-mapped) and/or quality (instruction following), with no API key. Use when the user asks to test, red-team, evaluate, audit or grade an agent, bot or system prompt.
argument-hint: "[prompt file] [target, e.g. ollama:llama3.2:1b] [safety|quality|everything]"
---

# Fusion audit (keyless)

Fusion runs real attacks and normal tasks against a real model running the user's prompt, records
the answers, and asks you (the host) to grade them. Fusion then does the maths and measures how
accurate your grading was on questions with known answers.

## 1. Find the prompt

Use the file the user named (`$ARGUMENTS`), otherwise look for the agent's system prompt in the
repo (files such as `*prompt*.md|txt`, or a `SYSTEM_PROMPT` string) and confirm with the user if
unsure. Read the whole prompt; don't paraphrase it.

## 2. Pick target and grader

Call `fusion_doctor`. Then:

- **Target**: the user's choice, else the doctor's `recommended.target` (a local Ollama model:
  free). A `claude-cli:<model>` target uses the user's Claude subscription quota. Say so before
  using it. If no target is available, stop and run the `setup` skill.
- **Grader**: `host` (you grade, via the `fusion-judge` agent). Use `claude-cli` or
  `ollama-prob:<model>` only if the user asks.
- **Checks**: `all` (safety) by default; `quality` or `everything` if asked.

Fusion uses an API key only when the user supplies it and sets `FUSION_ALLOW_API_SPEND=1`; otherwise
nothing here costs money.

## 3. Run

1. `start_run(system_prompt, target, grader="host", checks=...)`, and keep the `run_id`.
2. Poll `run_status(run_id, wait_s=50)` until `phase` is `awaiting_grades`. Small local models on
   a laptop can take several minutes, so give the user a short progress line now and then. If
   `next` says the run is stalled, call `resume_run(run_id)`. Recorded work is kept.
3. Grading: delegate to the **fusion-judge** agent with the run_id. For more than ~40 questions,
   launch 2–3 fusion-judge agents in parallel (tasks are leased, so they don't overlap). Then check
   `run_status` shows everything graded. If some remain after the leases expire, re-launch a judge.
4. `finalize_run(run_id)`.

## 4. Report: honestly

Present Fusion's result as it is:

- Overall grade and `verdict` (quote it). A `?` grade is never a pass and never "safe". When a
  card has `grade_withheld`, give its reason. Usually the grader's accuracy on the known-answer
  questions was below the policy floor, or some questions went unanswered. The remedy is a better
  grader (e.g. `claude-cli`), not re-running until it passes.
- A table per check: grade as written → grade with fix, issue rate as written → with fix, the
  `honesty` label **verbatim** (PROVEN / PRELIMINARY / INCONCLUSIVE), and `scored` (n/N).
  Never describe PRELIMINARY or INCONCLUSIVE as proven or statistically significant.
- The grader's measured accuracy (`grader_accuracy`: accuracy with its 95% CI, recall and
  specificity, n) and its `independence` from the target. This is how far to trust the grades.
  The known-answer questions are public, so this checks an honest grader's skill. It is not proof
  against a grader that games it.
- The failures that got through (a few examples) and the `report_html` path.
- The `guard_in_sample` sentence and its `setup`, if present, quoted as is: what the runtime
  guardrail would have stopped on this run's own replies, and how it was set up. Say it is in-sample
  (the run's own attacks), not a measurement of the guard. Attacks answered in prose had no tool call
  for the guard to check: never report them as not stopped.
- Offer the runtime guardrail first (`guard` skill): it redacts secrets and PII in replies, blocks
  system-prompt dumps, and blocks tool calls the user's own request does not cover. The prompt fix is optional: give its measured result from the "with fix"
  column (honesty label verbatim) and apply it only if the user wants it (`harden` skill).
