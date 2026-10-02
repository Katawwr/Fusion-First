"""Measure a grader's accuracy against deterministic oracles on the committed evidence transcripts.

    python scripts/judge_eval.py prepare --workspace W --run-id je-v1 --models llama3.2:1b
        -> a run to grade with `fusion run tasks/submit` (the fusion-judge agent) or `grade` below
    python scripts/judge_eval.py grade   --workspace W --run-id je-v1 --grader ollama-prob:qwen2.5:7b
    python scripts/judge_eval.py score   --workspace W --run-id je-v1 --models llama3.2:1b \
        --grader-label "claude-sonnet (host subagent)" --out evals/validation/v1/judge_eval_host.json

Labels are recomputed from the transcripts + oracles at scoring time; the run never contains them.
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

from fusion_first.runs.engine import RunDir  # noqa: E402
from fusion_first.validate.judge_eval import (  # noqa: E402
    JUDGE_CHECK,
    collect_items,
    prepare_run,
    score,
    write_report,
)
from fusion_first.validate.transcripts import STORE_DIR_DEFAULT, TranscriptStore  # noqa: E402


def _args(argv):
    p = argparse.ArgumentParser(prog="judge_eval")
    p.add_argument("cmd", choices=["prepare", "grade", "score"])
    p.add_argument("--workspace", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--experiments", default=",".join(JUDGE_CHECK))
    p.add_argument("--models", default="llama3.2:1b")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--grader", default=None, help="built-in grader spec for `grade`")
    p.add_argument("--grader-label", default="host")
    p.add_argument("--out", default=None)
    p.add_argument("--artifacts", default=None,
                   help="score: also export the grading artifacts here (commit them to make the result re-derivable)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = _args(argv)
    exps = [e for e in a.experiments.split(",") if e]
    models = [m for m in a.models.split(",") if m]
    items = collect_items(exps, models, a.n, TranscriptStore(ROOT / STORE_DIR_DEFAULT))
    if a.cmd == "prepare":
        rd = prepare_run(a.workspace, items, run_id=a.run_id)
        print(f"{rd.root}: {rd.state().n_tasks} questions ({len(items)} transcripts)")
        return 0
    rd = RunDir(pathlib.Path(a.workspace).resolve(), a.run_id)
    if a.cmd == "grade":
        from fusion_first.backends.resolve import build_grader_client, parse_grader
        from fusion_first.runs.engine import grade_with

        g = parse_grader(a.grader)
        res = asyncio.run(grade_with(rd, build_grader_client(g), label=g.label))
        print(json.dumps(res))
        return 0
    if a.artifacts:
        from fusion_first.validate.judge_eval import export_artifacts

        export_artifacts(rd, a.artifacts)
    rep = score(rd, items, a.grader_label)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    rep.update({"demonstration": False, "measured": _dt.date.today().isoformat(), "git_sha": sha,
                "models": models, "experiments": exps, "n_transcripts": len(items),
                "judge_prompt_version": rd.plan().judge_prompt_version})
    if a.out:
        write_report(a.out, rep)
        print(f"wrote {a.out}")
    for check, block in rep["checks"].items():
        g = block["grader"]
        print(f"{check:26} n={g['n']:3} unanswered={g['unanswered']} acc={g['accuracy']['point']:.2f} "
              f"recall={g['recall']['point']:.2f} spec={g['specificity']['point']:.2f} f1={g['f1']:.2f} "
              f"kappa={g['kappa']:.2f}")
        for name in ("naive_regex", "tuned_heuristic"):
            b = block.get(name, {})
            if "f1" in b:
                vs = b["vs_grader"]
                print(f"  vs {name:16} acc={b['accuracy']['point']:.2f} f1={b['f1']:.2f} "
                      f"(grader right/baseline wrong {vs['grader_right_baseline_wrong']}, "
                      f"reverse {vs['baseline_right_grader_wrong']}, McNemar p={vs['mcnemar_p']:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
