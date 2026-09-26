---
name: harden
description: Apply Fusion First's tested guard rules to an agent's system prompt (the fix the audit measured), and optionally re-audit. Use when the user wants to fix or harden a prompt after a Fusion audit.
argument-hint: "[prompt file] [checks]"
---

# Harden a prompt

1. Read the prompt file (`$ARGUMENTS` or the one just audited).
2. Call `harden_prompt(system_prompt, checks)`. It appends Fusion's guard block and is idempotent,
   so running it twice changes nothing.
3. Show the user the added block. Write the hardened prompt back to the file only when they agree
   (or asked for it up front).
4. The audit's "with fix" column already measured this exact hardened prompt. Say what it showed,
   using its honesty label verbatim. If the fix made a quality check worse, say so plainly: that
   is the fix's cost.
5. For runtime protection that holds even when the model slips, offer the `guard` skill.
