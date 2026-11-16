"""Development pilot for the request binder (`fusion_first/guardrail/binder.py`): which local model, if any, clears
the legitimate calls the binding rule blocks without clearing hijacked ones? On the step-5 rows, which are seen
(scored 2026-11-10): development only, never quoted. Dev-only; local Ollama only; no spend.

    python scripts/binder_dev.py plan                          # the size of the Ollama job per model
    python scripts/binder_dev.py pilot --models qwen2.5:7b     # ONE Ollama job, resumable; prints the table
    python scripts/binder_dev.py table                         # the table from the recorded answers, no call

Each row is one tool call with the user's request and the tool results so far. The guard runs as step 5 ran it
(`require_authorization=True`, the row's tool results as `untrusted_text`, its organisation domain allowlisted),
with and without the binder. The binder is asked only where the binding rule blocks; each answer is recorded under
the sha256 of the model and the exact chat sent, so a rerun asks nothing twice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.guardrail import GuardConfig, Guardrail, RequestBinder  # noqa: E402
from fusion_first.guardrail.binder import BinderUnavailable  # noqa: E402
from fusion_first.stats.paired import mcnemar_exact_p  # noqa: E402

ROWS = ROOT / "datasets/guard_step5/rows.v1.jsonl"
PILOT = ROOT / "evals/validation/v1/binder/dev/pilot.jsonl"
MODELS = ("qwen2.5:7b", "llama3.1:8b", "qwen2.5:3b")
VARIANT = "#"  # "<model>#explain" asks the same model with `RequestBinder(explain=True)`
NO_ANSWER = "no_answer"


def _jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _append(path: pathlib.Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def key_of(model: str, messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps([model, messages], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def binder_for(name: str, transport=None) -> RequestBinder:
    """The binder a pilot name stands for: an Ollama model, optionally followed by `#explain`."""
    model, _, variant = name.partition(VARIANT)
    if variant not in ("", "explain"):
        raise SystemExit(f"unknown variant {variant!r} in {name!r}")
    return RequestBinder(model, transport=transport, explain=variant == "explain")


def decide(row: dict, binder=None) -> bool:
    """True when the guard blocks the row's call, configured as step 5 configured it."""
    guard = Guardrail(GuardConfig(require_authorization=True, allowlisted_domains=[row["org_domain"]]), binder=binder)
    return guard.guard_tool_call(row["call"]["name"], row["call"]["arguments"], user_request=row["user_request"],
                                 untrusted_context=True, untrusted_text=row["tool_results"]).blocked


class Recorded:
    """A binder that answers from the record and, with `live`, asks the model for what is missing."""

    def __init__(self, model: str, answers: dict[str, object], live: RequestBinder | None = None, path=None):
        self.model, self.answers, self.live, self.path = model, answers, live, path
        self.shape = binder_for(model, transport=lambda path, payload: {})
        self.asked: list[str] = []  # the keys this row needed
        self.missing = False  # the guard swallows a binder's exception, so a missing answer is flagged here
        self.new = 0

    def __call__(self, user_request: str, name: str, arguments: dict) -> bool:
        key = key_of(self.model, self.shape.messages(user_request, name, arguments))
        self.asked.append(key)
        if key not in self.answers:
            if self.live is None:
                self.missing = True
                raise BinderUnavailable("no recorded answer")
            start = time.perf_counter()
            try:
                answer: object = self.live(user_request, name, arguments)
            except BinderUnavailable as exc:
                answer = f"{NO_ANSWER}: {exc}"
            self.answers[key] = answer
            self.new += 1
            _append(self.path, {"model": self.model, "key": key, "answer": answer,
                                "seconds": round(time.perf_counter() - start, 2)})
        answer = self.answers[key]
        if answer is True or answer is False:
            return answer
        raise BinderUnavailable(str(answer))


def run(model: str, rows: list[dict], *, live: bool, transport=None, path: pathlib.Path = PILOT) -> list[dict]:
    """Each row under the rules alone and with the binder: {id, label, binding_only, rules, binder, asked,
    answered}. `answered` is False for a row whose answer is not recorded (table only)."""
    answers = {r["key"]: r["answer"] for r in _jsonl(path) if r["model"] == model}
    binder = Recorded(model, answers, binder_for(model, transport) if live else None, path)
    out = []
    for row in rows:
        binder.asked, binder.missing = [], False
        with_binder = decide(row, binder)
        answered = not binder.missing
        with_binder = with_binder if answered else None
        out.append({"id": row["id"], "label": row["label"], "binding_only": row.get("binding_only", False),
                    "rules": decide(row), "binder": with_binder, "asked": len(binder.asked), "answered": answered})
    return out


def table(model: str, results: list[dict], seconds: list[float]) -> str:
    lines = [f"{model}  (development, seen rows, never quoted)"]
    for label in ("legitimate", "hijack"):
        rows = [r for r in results if r["label"] == label and r["answered"]]
        missing = sum(r["label"] == label and not r["answered"] for r in results)
        rules, binder = sum(r["rules"] for r in rows), sum(r["binder"] for r in rows)
        only_rules = sum(r["rules"] and not r["binder"] for r in rows)
        only_binder = sum(r["binder"] and not r["rules"] for r in rows)
        lines.append(f"  {label:10} n={len(rows):3}  blocked: rules {rules:3}  with binder {binder:3}  "
                     f"(cleared {only_rules}, newly blocked {only_binder}, p={mcnemar_exact_p(only_rules, only_binder):.3g})"
                     + (f"  [{missing} not answered yet]" if missing else ""))
    hard = [r for r in results if r["label"] == "hijack" and r["binding_only"] and r["answered"]]
    lines.append(f"  hijack, no address in the call: n={len(hard)}  blocked: rules {sum(r['rules'] for r in hard)}  "
                 f"with binder {sum(r['binder'] for r in hard)}")
    if seconds:
        ordered = sorted(seconds)
        lines.append(f"  {len(seconds)} answers recorded, median {ordered[len(ordered) // 2]:.2f} s, "
                     f"p95 {ordered[int(len(ordered) * 0.95) - 1]:.2f} s")
    return "\n".join(lines)


def _report(model: str, results: list[dict], path: pathlib.Path) -> str:
    records = [r for r in _jsonl(path) if r["model"] == model]
    none = sum(isinstance(r["answer"], str) for r in records)
    return table(model, results, [r["seconds"] for r in records]) + f"\n  answers that were no answer: {none}"


def main(argv: list[str] | None = None, *, transport=None, rows_path: pathlib.Path | None = None,
         pilot_path: pathlib.Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "pilot", "table"):
        sub.add_parser(name).add_argument("--models", nargs="+", default=list(MODELS))
    a = parser.parse_args(argv)
    rows, path = _jsonl(rows_path or ROWS), pilot_path or PILOT
    for model in a.models:
        if a.cmd == "plan":
            blocked = [r for r in rows if decide(r)]
            done = sum(r["answered"] for r in run(model, blocked, live=False, path=path))
            print(f"{model}: {len(rows)} rows, {len(blocked)} blocked by the rules; of those, {done} need no "
                  f"new answer (recorded, or not a binding block)")
            continue
        results = run(model, rows, live=a.cmd == "pilot", transport=transport, path=path)
        print(_report(model, results, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
