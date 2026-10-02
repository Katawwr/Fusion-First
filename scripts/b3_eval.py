"""B3: Fusion's rubric judge vs a plain single-question judge on the Q1 items (pre-registered in
evals/validation/v1/PREREG_b3_single_question.md).

    python scripts/b3_eval.py prepare --workspace W [--store DIR]
        -> W/tasks.json (question + transcript per opaque task id; no labels) for the graders
    python scripts/b3_eval.py record  --workspace W --file answers.json --grader host:sonnet
        -> validates [{"task_id", "unsafe"}] answers into W/b3_answers.json (one pass per task)
    python scripts/b3_eval.py score   --workspace W [--store DIR] \
        --out evals/validation/v1/b3_rubric_vs_plain_judge.json \
        --artifacts evals/validation/v1/b3_rubric_vs_plain_judge

The rubric judge's verdicts come from the committed Q1 artifacts (not re-run). `prepare` refuses to
run unless its items are exactly the Q1 items.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate.b3 import b3_tasks, record_answers, score_b3  # noqa: E402
from fusion_first.validate.judge_eval import ArtifactDir, _verdicts, collect_items  # noqa: E402
from fusion_first.validate.transcripts import STORE_DIR_DEFAULT, TranscriptStore  # noqa: E402

Q1_ARTIFACTS = ROOT / "evals/validation/v1/judge_eval_host_sonnet"
EXPERIMENTS = ("injecagent", "gandalf")
MODELS = ("llama3.2:1b",)


def _args(argv):
    p = argparse.ArgumentParser(prog="b3_eval")
    p.add_argument("cmd", choices=["prepare", "record", "score"])
    p.add_argument("--workspace", required=True)
    p.add_argument("--store", default=str(ROOT / STORE_DIR_DEFAULT))
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--file", default=None, help="record: answers JSON [{task_id, unsafe}]")
    p.add_argument("--grader", default="host:sonnet")
    p.add_argument("--out", default=None)
    p.add_argument("--artifacts", default=None)
    return p.parse_args(argv)


def _items(a):
    items = collect_items(EXPERIMENTS, MODELS, a.n, TranscriptStore(a.store))
    q1 = set(json.loads((Q1_ARTIFACTS / "items.json").read_text(encoding="utf-8")))
    if {i.uid for i in items} != q1:
        raise SystemExit(f"items differ from the Q1 set ({len(items)} vs {len(q1)}): refusing to run B3")
    return items


def main(argv=None) -> int:
    a = _args(argv)
    ws = pathlib.Path(a.workspace)
    ws.mkdir(parents=True, exist_ok=True)
    answers_path = ws / "b3_answers.json"

    if a.cmd == "prepare":
        secret_path = ws / ".secret"
        if not secret_path.exists():
            secret_path.write_text(secrets.token_hex(16), encoding="utf-8")
        tasks, task_uid = b3_tasks(_items(a), secret_path.read_text(encoding="utf-8").strip())
        (ws / "tasks.json").write_text(json.dumps(tasks, indent=1, ensure_ascii=False), encoding="utf-8")
        (ws / "task_uid.json").write_text(json.dumps(task_uid, indent=1), encoding="utf-8")
        print(f"{len(tasks)} B3 questions -> {ws / 'tasks.json'}")
        return 0

    if a.cmd == "record":
        task_uid = json.loads((ws / "task_uid.json").read_text(encoding="utf-8"))
        store = json.loads(answers_path.read_text(encoding="utf-8")) if answers_path.exists() else {}
        answers = json.loads(pathlib.Path(a.file).read_text(encoding="utf-8"))
        out = record_answers(answers, task_uid, store, grader=a.grader)
        answers_path.write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8")
        print(json.dumps({"accepted": len(out["accepted"]), "rejected": out["rejected"],
                          "answered": len(store), "of": len(task_uid)}))
        return 0

    items = _items(a)
    store = json.loads(answers_path.read_text(encoding="utf-8")) if answers_path.exists() else {}
    report = score_b3(items, store, _verdicts(ArtifactDir(Q1_ARTIFACTS), items))
    report.update({
        "demonstration": False,
        "generated_at": _dt.date.today().isoformat(),
        "items": "the 120 Q1 transcripts (llama3.2:1b; InjecAgent, Gandalf; both arms)",
        "rubric_grader": "Claude Sonnet (Claude Code subagent, fusion-judge rules): committed Q1 answers",
        "b3_grader": f"{a.grader} (Claude Code subagent, SingleQuestionJudge request only)",
        "preregistration": "evals/validation/v1/PREREG_b3_single_question.md",
    })
    if a.artifacts:
        art = pathlib.Path(a.artifacts)
        art.mkdir(parents=True, exist_ok=True)
        (art / "b3_answers.json").write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8",
                                             newline="\n")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote {a.out}")
    p = report["pooled"]
    print(f"pooled n={p['n']} rubric acc={p['rubric']['accuracy']['point']:.2f} "
          f"b3 acc={p['b3']['accuracy']['point']:.2f} diff={p['accuracy_difference']['point']:+.2f} "
          f"[{p['accuracy_difference']['low']:+.2f},{p['accuracy_difference']['high']:+.2f}] "
          f"p={p['mcnemar_p']:.3f} unanswered={p['b3_unanswered']} claim_allowed={report['decision']['claim_allowed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
