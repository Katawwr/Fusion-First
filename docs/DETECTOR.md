# Tool-result injection detector (v1)

A small CPU classifier that scores one untrusted text, such as a tool result, for injected instructions. It is
registered in [`evals/validation/v1/PREREG_detector_v1.md`](../evals/validation/v1/PREREG_detector_v1.md) and is
dev-only until its registered result is committed. If the registered rule is met it becomes an observe-only
`guard_input` signal: it adds an event and never changes a guard decision.

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

Filled when `evals/validation/v1/detector/detector_v1.json` is committed. Until then no number from this study is
claimed. The Trust Report (Q5) and the site's Trust page are generated from that file, and any number quoted here
will be registered in `evals/claims.yaml`.

## Limits

- Text-level detection only: nothing here measures attack success, task completion or the guard's cost in an agent
  loop. The AgentDojo cost result in the Trust Report stands.
- No adaptive-attack evaluation. A static result is expected to degrade against an attacker who adapts to the
  detector.
- InjecAgent shares 62 attacker instructions across its rows and AgentDojo one wrapper, so in-source numbers flatter
  any model. Only leave-one-source-out numbers are claimed.
- deepset is in-distribution with respect to its own training split. Its German rows are the only non-English data,
  so there is no multilingual claim.
- AgentDojo is dev-only: its held-out set is spent for the guard.
- Blind-authored negatives may be easier than real traffic; the InjecAgent minimal pairs and the carrier controls
  are reported beside them.
- At runtime the guard scores a frame without the request or the tool; the registered rows carry them where a source
  has them.

## What is and is not claimed

Claimed once committed: the registered decision and the numbers in `detector_v1.json`, quoted only through
`evals/claims.yaml`.

Not claimed: any development number, any in-source number as generalisation, robustness to adaptive attacks,
multilingual detection, fewer successful attacks, or that the detector blocks anything. It is observe-only; the guard's
rules keep the decision.

## Files

- `evals/validation/v1/PREREG_detector_v1.md`: the registration.
- `scripts/detector_data.py`, `scripts/detector_train.py`, `scripts/detector_lg3.py`, `scripts/detector_score.py`:
  build the rows, train, run Llama Guard 3, score the confirmatory rows once (dev-only).
- `fusion_first/validate/detector_*.py`: the systems, the evaluation and the confirmatory scorer;
  `fusion_first/validate/detector.py`: the guard callable.
- `fusion_first/guardrail/guard.py`: `Guardrail(detector=...)`, the observe-only event.
