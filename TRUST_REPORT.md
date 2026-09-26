# Fusion First — Trust Report

This report answers four questions about Fusion itself: **is it detecting accurately, does it error
often, does the fix work, and does it add value over simpler checks?** It is generated from committed
evidence files by `python -m fusion.validate.trust_report` — nothing here is typed by hand, and a test
fails if this file and its evidence disagree. Intervals are 95% Wilson (rates) unless noted. Evidence
from the offline stand-in judge (`demonstration: true`) is never used here.

## Q1 — Is the judge accurate?

NOT YET MEASURED — no committed judge-vs-oracle evidence.

## Q3 — Does the fix work, and what does it cost?

NOT YET MEASURED — the oracle-labelled evidence run on local open-weight models has not been committed yet.

## Runtime guard for Claude Code (fusion-guard hook)

Tool calls written by independent agents **blind to the rules**; each set scored once.

| Set | benign n | Prompted (over-block) | attack n | Caught (recall) | Caught, .test hosts as public | Status |
|---|---|---|---|---|---|---|
| v1 | 80 | 6% (3%–14%) | 60 | 65% (52%–76%) | — | PRE-TUNING |
| v2 | 100 | 5% (2%–11%) | 70 | 33% (23%–44%) | 61% (50%–72%) | HELD OUT at rules_git_sha |

Pattern rules catch the common exfiltration / destruction / remote-code shapes and miss much of the long tail; treat the hook as defense in depth, not a sandbox.

## Known limits

- Oracle labels decide narrow questions (a tool was called, a password appeared). Where the judge's rubric is broader than the oracle, some 'disagreements' are real violations the oracle can't see — see each disagreement audit.
- Samples are small (tens of transcripts per cell); read the intervals, not the points.
- Known-answer questions come from a public gold set; the in-run oracle cross-check covers only clear-cut questions.
