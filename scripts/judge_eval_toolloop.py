"""Judge accuracy on sealed gold blind splits: the grader vs deterministic oracles, one registered study at a time.

    python scripts/judge_eval_toolloop.py prepare --workspace W --run-id tl-v1                 # --study toolloop
        -> grade with `fusion run tasks --lease` / `fusion run submit` (host Sonnet subagents, one pass)
    python scripts/judge_eval_toolloop.py score   --workspace W --run-id tl-v1
        -> evals/validation/v1/toolloop/judge_eval_toolloop_host_sonnet.json (written once; never overwritten)
    python scripts/judge_eval_toolloop.py prepare --study claims_v3 --workspace W --run-id cv3-1
    python scripts/judge_eval_toolloop.py score   --study claims_v3 --workspace W --run-id cv3-1
        -> evals/validation/v1/claims_v3/judge_eval_claims_v3_host_sonnet.json

Registrations: evals/validation/v1/PREREG_q1_toolloop.md (toolloop), PREREG_q7_claims_v3.md (claims_v3). Labels are
recomputed from the committed gold at scoring time; the run never contains them. Both commands refuse unless every
blind split the study grades matches its seal.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.runs.engine import RunDir, RunError  # noqa: E402
from fusion_first.validate import judge_eval_toolloop as jt  # noqa: E402


def _args(argv):
    p = argparse.ArgumentParser(prog="judge_eval_toolloop", description=__doc__.splitlines()[0])
    p.add_argument("cmd", choices=["prepare", "score"])
    p.add_argument("--study", choices=sorted(jt.STUDIES), default="toolloop")
    p.add_argument("--workspace", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--out", default=None,
                   help="score: evidence path (relative to --root; default the study's); never overwritten")
    p.add_argument("--grader-label", default=None, help="default: the study's grader label")
    p.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)  # tests point this at a synthetic repo
    a = p.parse_args(argv)
    if a.out is None:
        a.out = jt.STUDIES[a.study].evidence
    return a


def main(argv=None) -> int:
    a = _args(argv)
    root = pathlib.Path(a.root)
    study = jt.STUDIES[a.study]
    try:
        if a.cmd == "prepare":
            rd = jt.prepare(a.workspace, root=root, run_id=a.run_id, study=study)
            print(f"{rd.root}: {rd.state().n_tasks} questions")
            return 0
        out = pathlib.Path(a.out)
        rep = jt.score(RunDir(pathlib.Path(a.workspace).resolve(), a.run_id),
                       out=out if out.is_absolute() else root / out, root=root, grader_label=a.grader_label,
                       study=study)
    except (FileExistsError, ValueError, RunError) as e:
        print(f"judge_eval_toolloop {a.cmd}: {e}", file=sys.stderr)
        return 1
    for check, block in rep["checks"].items():
        g = block["grader"]
        acc = g["accuracy"]
        print(f"{check:18} n={g['n']:3} unanswered={g['unanswered']} acc={acc['point']:.2f} "
              f"[{acc['low']:.2f}, {acc['high']:.2f}] recall={g['recall']['point']:.2f} "
              f"spec={g['specificity']['point']:.2f} f1={g['f1']:.2f} kappa={g['kappa']:.2f}")
        for name, sub in (block.get("subsets") or {}).items():
            print(f"  {name:16} n={sub['n']:3} unanswered={sub['unanswered']} acc={sub['accuracy']['point']:.2f} "
                  f"[{sub['accuracy']['low']:.2f}, {sub['accuracy']['high']:.2f}] f1={sub['f1']:.2f}")
    d = rep["decision"]
    print(f"decision: claim_allowed={d['claim_allowed']} ({d['rule']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
