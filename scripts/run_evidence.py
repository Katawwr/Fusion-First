"""Run and analyze the oracle-labelled evidence experiments on LOCAL open-weight models (free).

    python scripts/run_evidence.py plan    --n 30
    python scripts/run_evidence.py run     --n 30 --models llama3.2:1b,qwen2.5:1.5b,gemma3:1b,qwen2.5:3b
    python scripts/run_evidence.py analyze --n 30 --models ... --out evals/validation/v1/evidence_oracle.json

Only Ollama targets are used here: no API, no subscription calls. `run` is resumable: re-run the
same command after an interruption and it continues where it stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate.analysis import analyze, attack_success_by_model  # noqa: E402
from fusion_first.validate.experiments import (  # noqa: E402
    EXPERIMENTS,
    SPENT,
    SPENT_THROUGH_STEP2,
    build_items,
    iter_plan,
)
from fusion_first.validate.prereg import compact_decision  # noqa: E402
from fusion_first.validate.transcripts import (  # noqa: E402
    STORE_DIR_DEFAULT,
    TranscriptStore,
    generate,
)

DEFAULT_MODELS = "llama3.2:1b,qwen2.5:1.5b,gemma3:1b,qwen2.5:3b"
# Experiments whose oracle reads only the opening of a reply (over-refusal) use the short cap too;
# IFEval keeps the long cap because its verifiers check whole answers (length, sections...).
SHORT_CAP = {"xstest"}


def _args(argv):
    p = argparse.ArgumentParser(prog="run_evidence")
    p.add_argument("cmd", choices=["plan", "run", "analyze"])
    p.add_argument("--experiments", default=",".join(EXPERIMENTS))
    p.add_argument("--models", default=DEFAULT_MODELS)
    p.add_argument("--n", type=int, default=30, help="items per experiment")
    p.add_argument("--max-tokens", type=int, default=600, help="cap for quality experiments")
    p.add_argument("--max-tokens-safety", type=int, default=256,
                   help="cap for safety experiments (the oracle only needs the first lines)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--store", default=str(ROOT / STORE_DIR_DEFAULT))
    p.add_argument("--out", default=str(ROOT / "evals/validation/v1/evidence_oracle.json"))
    p.add_argument("--stop-after", type=int, default=None, help="generate at most this many (smoke)")
    p.add_argument("--arms", default="baseline,hardened",
                   help="run: arms to generate; analyze: exactly two, reference first (e.g. baseline,compact)")
    p.add_argument("--salt", default="fusion-evidence-v1", help="item sample salt")
    p.add_argument("--exclude-spent", action="store_true",
                   help="drop every item of the samples step 2 excluded (experiments.SPENT)")
    p.add_argument("--exclude-spent-through-step2", action="store_true",
                   help="... and step 2's own sample (experiments.SPENT_THROUGH_STEP2)")
    p.add_argument("--exclude-salt", default=None,
                   help="drop every item of this other sample (same --n) so the items are fresh and disjoint")
    return p.parse_args(argv)


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv=None) -> int:
    a = _args(argv)
    exps = [e.strip() for e in a.experiments.split(",") if e.strip()]
    arms = tuple(x.strip() for x in a.arms.split(",") if x.strip())
    exclude = (SPENT_THROUGH_STEP2 if a.exclude_spent_through_step2 else SPENT if a.exclude_spent
               else (a.exclude_salt, a.n) if a.exclude_salt else None)
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    store = TranscriptStore(a.store)

    if a.cmd == "plan":
        for e in exps:
            print(f"{e}: {len(build_items(e, a.n, salt=a.salt, exclude=exclude))} items")
        total = len(list(iter_plan(exps, a.n, models, arms=arms, salt=a.salt, exclude=exclude)))
        print(f"total generations: {total} ({len(models)} models x {len(arms)} arms)")
        return 0

    if a.cmd == "run":
        from fusion_first.model.providers.ollama import OllamaModelClient, ollama_available

        if not ollama_available():
            print("Ollama is not reachable at 127.0.0.1:11434: start `ollama serve`.")
            return 2

        def client_for(model: str):
            return OllamaModelClient(model=model, num_ctx=8192, timeout=600)

        counts = asyncio.run(generate(
            iter_plan(exps, a.n, models, arms=arms, salt=a.salt, exclude=exclude), client_for, store,
            max_tokens=a.max_tokens, seed=a.seed,
            on_progress=lambda s: print(s, flush=True), stop_after=a.stop_after,
            max_tokens_for=lambda it: a.max_tokens_safety if (it.kind == "safety" or it.experiment in SHORT_CAP)
            else a.max_tokens,
        ))
        print(json.dumps(counts))
        return 0

    from fusion_first.model.providers.ollama import model_digest
    from fusion_first.validate.seal import remedies_hash

    if len(arms) != 2:
        print("analyze compares exactly two arms, e.g. --arms baseline,compact")
        return 2
    items_by_exp = {e: build_items(e, a.n, salt=a.salt, exclude=exclude) for e in exps}
    result = analyze(items_by_exp, models, store, arms)
    result["attack_success_by_model"] = attack_success_by_model(items_by_exp, models, store, arms)
    if arms == ("baseline", "compact"):
        # The pre-registered rule (evals/validation/v1/PREREG_compact_fix.md), applied in code.
        result["prereg_decision"] = compact_decision(result["attack_success_by_model"], result["cells"])
    sources = (ROOT / "datasets/external/SOURCES.yaml")
    out = {
        "demonstration": False,
        "kind": "oracle-labelled evidence on local open-weight models",
        "generated_at": _dt.date.today().isoformat(),
        "git_sha": _git_sha(),
        "remedies_hash": remedies_hash(),
        "models": {m: model_digest(m) for m in models},
        "n_per_experiment": a.n,
        "max_tokens": {"quality": a.max_tokens, "safety": a.max_tokens_safety,
                       "short_cap_experiments": sorted(SHORT_CAP),
                       "note": "each transcript record stores the cap it was generated with"},
        "seed": a.seed,
        "sample": {"salt": a.salt, "exclude_salt": a.exclude_salt, "exclude_spent": a.exclude_spent,
                   "exclude_spent_through_step2": a.exclude_spent_through_step2},
        "sources_manifest": str(sources.relative_to(ROOT)),
        **result,
    }
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {a.out}")
    for c in result["cells"]:
        br, hr = c["baseline_rate"], c["hardened_rate"]
        print(f"  {c['experiment']:10} {c['model']:14} n={c['n_paired']:3} base={br['point']:.0%} "
              f"hard={hr['point']:.0%} [{c['before_after'].get('honesty', '-')}] "
              f"unscored={c['n_unscored']} undecidable={c['n_undecidable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
