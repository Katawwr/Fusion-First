# Tool-result injection detector (v1)

A small CPU classifier that scores one untrusted text, such as a tool result, for injected instructions. It is
registered in [`evals/validation/v1/PREREG_detector_v1.md`](../evals/validation/v1/PREREG_detector_v1.md). The
registered rule was not met (see [Registered result](#registered-result)), so it stays dev-only. Had it been met, the
detector would have become an observe-only `guard_input` signal: an event that never changes a guard decision.

## Why train one

`guard_input` flags injection with a 22-phrase substring list (`_INJECTION_PHRASES` in
`fusion_first/guardrail/guard.py`) over the raw text and its normalized views. The list has no registered evidence,
and the code leaves paraphrased and non-English injection to a judge that is not on the runtime path.

A read-only development re-run of the list (diagnostic, not registered) matched 0 of 1,054 InjecAgent injected tool
responses, 8 of 263 deepset positives and 0 of 200 BIPIA payloads. Injected tool results rarely use the phrases it
looks for. The study asks whether a model given the request, the tool name and the tool result together does better
on injected tool results from a source it never trained on, without more false alarms on benign tool results.

## Data and labels

Labels are mechanical (a known injected payload, its clean counterpart, or the dataset's own label), never judge
labels. Rows are built by `scripts/detector_data.py` into `datasets/detector/v1/{dev,confirmatory}.jsonl`; counts
are in `datasets/detector/v1/manifest.json`.

| Source | Positive | Negative | Split |
|---|---|---|---|
| InjecAgent | the tool response carrying the attacker instruction | its exact minimal pair, the placeholder filled by a blind benign filler | confirmatory: the 744 ids outside every sample already spent; dev: the 310 spent ids |
| deepset prompt-injection | a labelled injection prompt | a labelled benign prompt | train split = dev, test split = confirmatory (in-distribution) |
| BIPIA | a payload inside a blind-authored benign carrier | the same carrier without a payload | BIPIA train payloads = dev, test = confirmatory; carriers by hash |
| AgentDojo | a tool result from an attacked run | a clean tool result from the unattacked run | dev and leave-one-source-out only |
| Blind negatives | none | benign tool results written by subagents that never saw the positives, the list or the detector | dev or confirmatory |

The confirmatory split was sealed (`evals/validation/v1/detector/confirmatory.seal.json`) before any model was
trained: 1,946 rows, 929 positives (744 InjecAgent, 125 BIPIA in carriers, 60 deepset) and 1,017 distinct negatives
(744 InjecAgent minimal pairs, 148 blind, 69 carrier controls, 56 deepset). Exact duplicates are dropped across
sources, and no text or id appears in both splits. The scorer refuses the confirmatory rows unless they match the seal.

## The frame

Every system sees one text in one frame:

```text
[REQUEST] <user request or (none)> [TOOL] <tool name or (none)> [RESULT] <text>
```

Positives and negatives share the frame, so no system can learn the wrapper. A frame longer than 256 tokens is cut
into 256-token windows with stride 128 and scores the maximum over its chunks. Chunks of long training positives are
labelled by where the injected span falls (`fusion_first/validate/detector_systems.py`).

The phrase list scores the raw tool result, as `guard_input` does. At runtime `guard_input` sees only the untrusted
text, so `fusion_first.validate.detector.load_detector` scores a frame with `(none)` for the request and the tool.

## Leave-one-source-out

Each fold holds out one of five sources: InjecAgent, deepset, BIPIA, AgentDojo or the blind negatives. A source is
scored by the model trained without it, at a threshold fixed on the training sources' dev negatives only: the lowest
threshold that flags at most 1 in 100 of them. The dev table and its thresholds
(`evals/validation/v1/detector/dev_loso.json`) are diagnostic.

One all-sources model, trained before the confirmatory pass, is scored as its own arm. It is the model the guard
would load. It saw every source in training, so its rows are in-source and never the primary recall.

## Baselines and arms

| Arm | What it is | Decision |
|---|---|---|
| B0 | always negative | never flags |
| B1 | the shipped phrase list over normalized views | flags on a match |
| B2 | Llama Guard 3 8B (local), configured with a prompt-injection category, and off the shelf | an "unsafe" verdict flags; its own stratified subsample with its own n |
| B3 | ProtectAI deberta-v3-base-prompt-injection-v2 | run only if the owner approves the download; otherwise absent and named |
| E | frozen `BAAI/bge-small-en-v1.5` embeddings and a class-balanced logistic regression | the registered operating point |
| F | optional fine-tune of bge-small | the registered operating point |

The registered decision (`fusion_first.validate.prereg.detector_decision`) adopts the detector as an observe-only
`guard_input` signal only if both hold:

1. recall on the 744 confirmatory InjecAgent positives, under the fold that never saw InjecAgent, is at least 0.60;
2. the shipped all-sources model's false-positive rate on the 961 distinct confirmatory tool-result negatives (744
   InjecAgent minimal pairs, 148 blind, 69 carrier controls) is at most 0.05.

Otherwise the detector stays dev-only. McNemar against the phrase list is reported, but it is not the bar.

## Latency

CPU p50 and p95 per decision for every arm, timed over every chunk of a text. Llama Guard 3 latency is Ollama's wall
time per reply.

## Registered result

Scored once on the sealed confirmatory rows at git `90b4cc7`. Evidence:
[`evals/validation/v1/detector/detector_v1.json`](../evals/validation/v1/detector/detector_v1.json). The Trust
Report (Q5) and the site's Trust page show every arm by source with 95% Wilson intervals.

Registered decision: not adopted; the detector stays dev-only.

- Primary (1), arm E under the fold that never saw InjecAgent, against a bar of at least 0.60:
  flagged 0 of 744 never-seen InjecAgent injections, recall 0.0% (95% CI 0.0% to 0.5%).
- Primary (2), the shipped all-sources model, against a bar of at most 0.05:
  flagged 4 of 961 distinct benign tool results, false-positive rate 0.4% (95% CI 0.2% to 1.1%).
- The phrase list flagged 0 of 744 on the same InjecAgent rows.

| Arm | InjecAgent injections flagged | Benign tool results flagged | InjecAgent AUROC | p50 latency |
|---|---|---|---|---|
| B0 always negative | 0 of 744 (0.0%) | 0 of 961 (0.0%) | 0.50 | – |
| B1 phrase list (shipped) | 0 of 744 (0.0%) | 0 of 961 (0.0%) | 0.50 | 0.18 ms |
| E embedding, leave-one-source-out | 0 of 744 (0.0%) | 6 of 961 (0.6%) | 0.55 | – |
| E embedding, all sources, shipped (in-source) | 157 of 744 (21.1%) | 4 of 961 (0.4%) | 0.92 | 48 ms |
| F fine-tune, hold-out-InjecAgent fold | 73 of 744 (9.8%) | 22 of 961 (2.3%) | 0.81 | – |
| F fine-tune, all sources (in-source) | 744 of 744 (100.0%) | 13 of 961 (1.4%) | 1.00 | 43 ms |
| B2 Llama Guard 3, configured | 8 of 28 (28.6%) | 0 of 86 (0.0%) | 0.64 | 7.4 s |
| B2 Llama Guard 3, off the shelf | 6 of 14 (42.9%) | 3 of 43 (7.0%) | 0.61 | 7.2 s |

The table is generated from the evidence (`fusion_first.validate.trust_report.detector_doc_table`) and a test checks
it here. Benign tool results are the 961 tool-result negatives (744 InjecAgent minimal pairs, 148 blind, 69 carrier
controls); a Llama Guard 3 arm counts those in its own stratified subsample. The fold arms have no latency of their
own in the evidence, which gives it as the matching all-sources model's.

On never-seen InjecAgent injections the registered embedding arm and the phrase list flag none; the fine-tune fold
and Llama Guard 3 flag some, Llama Guard 3 on small subsamples. The all-sources models trained on the dev InjecAgent
rows, which share the 62 attacker instructions and 17 tool-result templates with the confirmatory rows: that is the
in-source caveat the registration states, and their rows are not claimed. B3 (ProtectAI) was not run: its model
download needs the owner's approval.

## Limits

- Text-level detection only: nothing here measures attack success, task completion or the guard's cost in an agent
  loop. The AgentDojo cost result in the Trust Report stands.
- No adaptive-attack evaluation. A static result is expected to degrade against an attacker who adapts to the
  detector.
- InjecAgent's 62 attacker instructions and 17 tool-result templates appear in both the dev and the confirmatory
  rows, and AgentDojo shares one wrapper, so in-source numbers flatter any model. Only leave-one-source-out numbers
  are claimed.
- Arm F registers only the hold-out-InjecAgent and hold-out-AgentDojo folds, so its BIPIA, deepset and blind rows are
  scored by the hold-out-InjecAgent fold, which trained on those sources: they are in-source.
- deepset is in-distribution with respect to its own training split. Its German rows are the only non-English data,
  so there is no multilingual claim.
- AgentDojo is dev-only: its held-out set is spent for the guard.
- Blind-authored negatives may be easier than real traffic; the InjecAgent minimal pairs and the carrier controls
  are reported beside them.
- At runtime the guard scores a frame without the request or the tool; the registered rows carry them where a source
  has them.

## What is and is not claimed

Claimed: the registered decision and the numbers quoted under Registered result, each registered in
`evals/claims.yaml` against `detector_v1.json`.

Not claimed: any development number, any in-source number as generalisation, robustness to adaptive attacks,
multilingual detection, fewer successful attacks, or that the detector blocks anything. It is observe-only; the guard's
rules keep the decision.

## Files

- `evals/validation/v1/PREREG_detector_v1.md`: the registration; `evals/validation/v1/PREREG_LEDGER.md` shows its
  commit preceding every evidence file.
- `evals/validation/v1/detector/detector_v1.json`: the registered result, with the per-row `scores.jsonl` and Llama
  Guard 3's `lg3_raw.jsonl` and `lg3_subsample.json`; `dev_loso.json` is diagnostic.
- `scripts/detector_data.py`, `scripts/detector_train.py`, `scripts/detector_lg3.py`, `scripts/detector_score.py`:
  build the rows, train, run Llama Guard 3, score the confirmatory rows once (dev-only).
- `fusion_first/validate/detector_*.py`: the systems, the evaluation and the confirmatory scorer;
  `fusion_first/validate/detector.py`: the guard callable.
- `fusion_first/guardrail/guard.py`: `Guardrail(detector=...)`, the observe-only event.
