---
name: harden
description: Optional prompt fix. Append Fusion First's prompt-fix block to an agent's system prompt and report what the audit measured for it. Use when the user asks to fix or harden a prompt after a Fusion audit; offer the runtime guardrail (guard skill) first.
argument-hint: "[prompt file] [checks]"
---

# Optional prompt fix

On the small open-weight models measured, the prompt fix rarely cut attacks and raised refusals of safe
requests (Trust Report). The runtime guardrail (`guard` skill) is the measured protection; offer it
first.

1. Read the prompt file (`$ARGUMENTS` or the one just audited).
2. Call `harden_prompt(system_prompt, checks)`. It appends Fusion's fix block and is idempotent, so
   running it twice changes nothing.
3. Show the user the added block. Write the hardened prompt back to the file only when they agree
   (or asked for it up front).
4. The audit's "with fix" column measured this exact hardened prompt on the target model. Say what it
   showed, using its honesty label verbatim. If the fix let more attacks through or made a quality
   check worse, say so plainly and advise against shipping it.
