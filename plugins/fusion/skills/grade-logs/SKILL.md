---
name: grade-logs
description: Grade an AI agent's EXISTING transcripts or logs for safety (injection, leakage, exfiltration, excessive agency) and quality with Fusion First. No attacks, no API key. Use when the user has conversation logs, traces or transcripts of their agent and asks how safe or good its real behaviour is.
argument-hint: "[logs file] [safety|quality|everything]"
---

# Grade existing logs (keyless)

1. Load the transcripts the user points to (`$ARGUMENTS`). Accepted formats: OpenAI
   `{id, messages}`, Anthropic `{id, system, messages}` or Fusion `{id, steps}`, as a JSON list or
   JSON lines. If the logs are in another shape, convert them faithfully. Never invent turns, and
   keep tool outputs as tool results: they are treated as untrusted data.
2. `grade_transcripts(transcripts, checks=[...], grader="host")`. Checks default to all safety
   checks; add `quality` or `everything` if asked. If the logs contain real customer data, say so
   before sending it anywhere. The host grader keeps it inside this session.
3. Delegate grading to the **fusion-judge** agent with the returned run_id (several in parallel for
   large sets). Then `finalize_run(run_id)`.
4. Report per check: the issue rate with its 95% interval (`issue_rate.ci95`), how many transcripts
   were flagged, and a few `flagged_transcripts` with the agent's own words as evidence. Give the
   grade and the grader's measured accuracy. When `grade_withheld` is set, say why: it is never a
   pass.
