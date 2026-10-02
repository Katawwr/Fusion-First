# Pre-registration: compact prompt fix for small open-weight models

Registered 2026-09-26, before any compact-fix transcript was generated.

## Why

The first fix-efficacy evidence (`evidence_oracle.json`, commit 6061aa2) showed that Fusion's full
guard block (about 1,800 characters appended to the system prompt) did not reduce attacks on
llama3.2:1b. It also significantly increased refusals of safe requests (XSTest 10% to 33%,
McNemar p = 0.039).

## Hypothesis

A compact block (a few short lines, ending with an instruction to otherwise help normally) reduces
attack success on small models without the over-refusal cost of the full block.

## Design (fixed before data)

- **Arms:** `baseline` (the prompt as written), `hardened` (the full block, as shipped), `compact` (the
  compact block, `apply_fix(..., style="compact")`).
- **Items:** 30 per experiment, sampled with salt `fusion-evidence-compact-v1` and EXCLUDING every
  item used in `evidence_oracle.json` (salt `fusion-evidence-v1`), so no item the fix was designed
  after is reused. Same four experiments and oracles: InjecAgent, Gandalf, XSTest, IFEval.
- **Models:** llama3.2:1b first, then qwen2.5:1.5b, gemma3:1b and qwen2.5:3b as time allows. Seed 7,
  and the same token caps as the v1 run.
- **Primary outcomes** (compact vs baseline, paired McNemar, two-sided alpha 0.05, per model):
  1. Attack success (InjecAgent + Gandalf pooled) is lower with `compact`.
  2. Over-refusal (XSTest) with `compact` is non-inferior to baseline, within 10 percentage points
     (upper bound of the 95% CI of the increase is 0.10 or less).
- **Secondary:** compact vs hardened on both outcomes; IFEval defect rate (non-inferiority, same
  margin).
- **Decision rule:** the compact block becomes the default for small models ONLY if both primary
  outcomes hold on at least one model and no model shows a significant attack-success increase. The
  result is reported either way, including failure.

## What will not be done

- The compact text will not be tuned after seeing these transcripts. Any revision needs a new salt
  and a new pre-registration.
- These items will not be reused to evaluate later remedies.
