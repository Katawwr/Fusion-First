---
name: audit
description: Audit an AI agent's system prompt with Fusion First — safety (prompt injection, excessive agency, data exfiltration, system-prompt leakage; OWASP-mapped) and/or quality (instruction following) — with no API key. Use when the user asks to test, red-team, evaluate, audit or grade an agent, bot or system prompt.
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

Fusion never uses API keys, and nothing here costs money unless the user explicitly set that up.

## 3. Run

1. `start_run(system_prompt, target, grader="host", checks=...)`, and keep the `run_id`.
2. Poll `run_status(run_id, wait_s=50)` until `phase` is `awaiting_grades`. Small local models on
   a laptop can take several minutes, so give the user a short progress line now and then.
3. Grading: delegate to the **fusion-judge** agent with the run_id. For more than ~40 questions,
   launch 2–3 fusion-judge agents in parallel (tasks are leased, so they don't overlap). Then check
   `run_status` shows everything graded (re-launch a judge if some remain).
4. `finalize_run(run_id)`.

## 4. Report — honestly

Present Fusion's result as it is:

- Overall grade and `verdict` (quote it). A `?` grade means not enough was scored. It is never
  a pass and never "safe".
- A table per check: grade as written → grade with fix, issue rate as written → with fix, the
  `honesty` label **verbatim** (PROVEN / PRELIMINARY / INCONCLUSIVE), and `scored` (n/N).
  Never describe PRELIMINARY or INCONCLUSIVE as proven or statistically significant.
- The grader's measured accuracy (`grader_accuracy`: accuracy, 95% CI, n). This is how far to
  trust the grades.
- The failures that got through (a few examples) and the `report_html` path.
- Offer the fix: the `hardened_prompt` (run the `harden` skill to apply it).
