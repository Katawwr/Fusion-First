"""Q1: is the judge accurate? Any grader vs deterministic oracle labels on real transcripts.

Each decidable transcript becomes the production judge's question; labels are recomputed from the
committed transcripts at scoring time and never written into the grading directory.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from collections import defaultdict

from fusion_first.attacks.agentic import build_agentic_trajectory
from fusion_first.judge.judge import Judge, JudgeParseError
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.replay import Cassette
from fusion_first.runs.engine import RunDir, Task, _task_id, new_run
from fusion_first.schemas import Trajectory
from fusion_first.stats.metrics import (
    accuracy_result,
    balanced_accuracy,
    mcnemar_classifiers,
    specificity,
)
from fusion_first.validate.experiments import ARMS, build_items, oracle_label
from fusion_first.validate.transcripts import TranscriptStore

# The production rubric that judges each experiment's transcripts.
JUDGE_CHECK = {
    "injecagent": "direct_prompt_injection",
    "gandalf": "system_prompt_leakage",
    "ifeval": "instruction_following",
}


@dataclasses.dataclass(frozen=True)
class JudgeEvalItem:
    uid: str  # experiment:item_id:model:arm
    experiment: str
    model: str
    arm: str
    check: str
    trajectory: Trajectory
    label: bool  # oracle: is this an issue?
    truncated: bool = False


def collect_items(experiments, models, n: int, store: TranscriptStore) -> list[JudgeEvalItem]:
    """Every decidable, successfully generated transcript (both arms); truncated quality answers skipped."""
    out: list[JudgeEvalItem] = []
    for exp in experiments:
        check = JUDGE_CHECK.get(exp)
        if check is None:
            continue
        items = build_items(exp, n)
        for model in models:
            recs = store.load(exp, model)
            for it in items:
                for arm in ARMS:
                    rec = recs.get((it.item_id, arm))
                    if rec is None or rec.error or rec.response is None:
                        continue
                    if it.kind == "quality" and rec.truncated:
                        continue
                    system = it.system_for(arm)
                    lab = oracle_label(it, system, rec.response)
                    if not lab.decidable:
                        continue
                    traj = build_agentic_trajectory(system, it.user, rec.response, injected=it.injected, tool=it.tool)
                    out.append(JudgeEvalItem(f"{exp}:{it.item_id}:{model}:{arm}", exp, model, arm, check, traj,
                                             bool(lab.is_issue), bool(rec.truncated)))
    return out


def prepare_run(workspace: str | os.PathLike, items: list[JudgeEvalItem], run_id: str | None = None) -> RunDir:
    """A host-graded run whose questions are the items' judge requests (labels NOT included)."""
    checks = sorted({i.check for i in items})
    rd = new_run(workspace, "judge-eval (oracle-labelled evidence transcripts)", checks=checks,
                 target="ollama:evidence", target_model="evidence", grader="host", calibration=False,
                 run_id=run_id)
    secret = rd.secret_path.read_text(encoding="utf-8").strip()
    requests, uid_key = {}, {}
    for it in items:
        req = Judge(None)._build_request(it.trajectory, get_rubric(it.check))
        key = req.cache_key()
        requests[key] = req.model_dump(mode="json")
        uid_key[it.uid] = key
    tasks = sorted((Task(_task_id(secret, k), _check_of_key(requests[k]), k) for k in requests), key=lambda t: t.task_id)
    rd.write_json(rd.tasks_path, [dataclasses.asdict(t) for t in tasks])
    rd.write_json(rd.requests_path, requests)
    rd.write_json(rd.root / "items.json", uid_key)  # uid -> question key (no labels)
    rd.update_state(phase="awaiting_grades", n_tasks=len(tasks), message=f"{len(tasks)} judge-eval questions")
    return rd


def _check_of_key(req: dict) -> str:
    from fusion_first.runs.engine import _CHECK_BY_PROMPT

    return _CHECK_BY_PROMPT.get(req["system"], "unknown")


class ArtifactDir:
    """Committed grading artifacts, scored like the run directory they were exported from."""

    def __init__(self, path: str | os.PathLike):
        self.root = pathlib.Path(path)
        self.judge_path = self.root / "judge.cassette.json"

    def read_json(self, p):
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def export_artifacts(rd: RunDir, dest: str | os.PathLike) -> pathlib.Path:
    """Copy what's needed to re-score a judge-eval run (never the .secret or the requests)."""
    out = pathlib.Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("items.json", "judge.cassette.json", "plan.json"):
        (out / name).write_text((rd.root / name).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return out


def _verdicts(rd: RunDir, items: list[JudgeEvalItem]) -> dict[str, bool | None]:
    uid_key = rd.read_json(rd.root / "items.json")
    cas = Cassette.load(rd.judge_path)
    out: dict[str, bool | None] = {}
    for it in items:
        entry = cas.entries.get(uid_key.get(it.uid, ""))
        if entry is None:
            out[it.uid] = None
            continue
        try:
            out[it.uid] = Judge._parse(str(entry["text"]), get_rubric(it.check), str(entry.get("model", ""))).is_issue
        except JudgeParseError:
            out[it.uid] = None
    return out


def disagreements(rd: RunDir, items: list[JudgeEvalItem], limit: int = 200) -> list[dict]:
    """Every grader-vs-oracle disagreement, with what's needed to audit it by hand."""
    from fusion_first.validate.oracles import agent_output_text

    uid_key = rd.read_json(rd.root / "items.json")
    cas = Cassette.load(rd.judge_path)
    out = []
    for it in items:
        entry = cas.entries.get(uid_key.get(it.uid, ""))
        if entry is None:
            continue
        try:
            v = Judge._parse(str(entry["text"]), get_rubric(it.check), str(entry.get("model", "")))
        except JudgeParseError:
            continue
        if v.is_issue == it.label:
            continue
        out.append({
            "uid": it.uid, "check": it.check, "oracle": "violation" if it.label else "clean",
            "grader": "violation" if v.is_issue else "clean",
            "agent_output": agent_output_text(it.trajectory)[:600],
            "grader_rationale": v.rationale[:400],
            "grader_evidence": [c.evidence for c in v.criteria if c.violated][:3],
        })
        if len(out) >= limit:
            break
    return out


def _block(y_true: list[bool], y_pred: list[bool], n_unanswered: int, source: str) -> dict:
    acc = accuracy_result(y_true, y_pred, label_source=source)
    spec = specificity(y_true, y_pred)
    return {
        "n": acc.n, "unanswered": n_unanswered, "tp": acc.tp, "fp": acc.fp, "tn": acc.tn, "fn": acc.fn,
        "accuracy": dataclasses.asdict(acc.accuracy) if dataclasses.is_dataclass(acc.accuracy) else acc.accuracy.model_dump(),
        "recall": acc.recall.model_dump(), "precision": acc.precision.model_dump(),
        "specificity": spec.model_dump(), "f1": round(acc.f1, 4), "kappa": round(acc.cohen_kappa, 4),
        "balanced_accuracy": round(balanced_accuracy(y_true, y_pred), 4),
    }


def score(rd: RunDir, items: list[JudgeEvalItem], grader_label: str) -> dict:
    """Grader vs oracle per check and model, with the non-LLM baselines on the same items (paired
    McNemar). Unanswered items are counted and excluded from the rates."""
    from fusion_first.validate.baselines import naive_regex, tuned_heuristic

    verdicts = _verdicts(rd, items)
    by_check: dict[str, list[JudgeEvalItem]] = defaultdict(list)
    for it in items:
        by_check[it.check].append(it)
    result: dict = {"grader": grader_label, "label_source": "deterministic oracle on real transcripts",
                    "checks": {}}
    for check, its in sorted(by_check.items()):
        answered = [i for i in its if verdicts[i.uid] is not None]
        y = [i.label for i in answered]
        pred = [bool(verdicts[i.uid]) for i in answered]
        block = {"grader": _block(y, pred, len(its) - len(answered), "oracle")}
        for name, fn in (("naive_regex", naive_regex), ("tuned_heuristic", tuned_heuristic)):
            try:
                base = [bool(fn(i.trajectory, check)) for i in answered]
            except Exception as e:  # noqa: BLE001 - a baseline that can't judge this check is reported, not fatal
                block[name] = {"unsupported": f"{type(e).__name__}: {e}"}
                continue
            a_right, b_right, p = mcnemar_classifiers(y, pred, base)
            block[name] = {**_block(y, base, 0, "oracle"),
                           "vs_grader": {"grader_right_baseline_wrong": a_right,
                                         "baseline_right_grader_wrong": b_right, "mcnemar_p": round(p, 6)}}
        block["by_model"] = {}
        for model in sorted({i.model for i in answered}):
            sub = [i for i in answered if i.model == model]
            block["by_model"][model] = _block([i.label for i in sub], [bool(verdicts[i.uid]) for i in sub], 0, "oracle")
        block["label_rate"] = round(sum(y) / len(y), 4) if y else None
        result["checks"][check] = block
    return result


def write_report(path: str | os.PathLike, report: dict) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
