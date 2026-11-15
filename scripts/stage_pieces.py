"""Development pilot for three weaknesses the stage-hardening study showed (2026-11-14): the stage wrongly flags
more safe prompts that carry markup; a harmless question appended to a request halves detection; a request hidden
in tag characters is caught half the time. Seen prompts only, never quoted. Dev-only; local Ollama only; no spend.

    python scripts/stage_pieces.py plan     # the size of the Ollama job
    python scripts/stage_pieces.py pilot    # ONE Ollama job, resumable; prints the table

Three questions:
- markup: which way of writing an angle bracket costs least? The 400 prompts of the stage-hardening study (now
  seen) with the markup suffix, rendered with brackets as ( ), as [ ] and as spaces.
- sentences: what does `LlamaGuard(sentences=True)` cost on ordinary multi-sentence text? The first IFEval prompts,
  whole and sentence by sentence.
- dilution and hidden text: replayed from the study's recorded replies, no call (`replay`).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.guardrail import stages  # noqa: E402
from fusion_first.guardrail.stages import LLAMA_GUARD_MODEL, LlamaGuard, parse_verdict  # noqa: E402
from fusion_first.validate import experiments  # noqa: E402
from fusion_first.validate import stage_hardening as sh  # noqa: E402

PILOT = ROOT / "evals/validation/v1/stage_pieces/dev/pilot.jsonl"
STUDY_RAW = ROOT / "evals/validation/v1/stage_hardening/lg_raw.jsonl"
DATA_ROOT = None
N_SENTENCES = 100  # IFEval prompts for the sentence question; the rest stay unseen
BRACKETS = {"paren": ("(", ")"), "square": ("[", "]"), "space": (" ", " ")}
MARKUP = sh.BENIGN_FORMS["markup"]


def _study():
    spec = importlib.util.spec_from_file_location("stage_hardening_script", ROOT / "scripts" / "stage_hardening.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextlib.contextmanager
def brackets(name: str):
    """The stage with angle brackets written as `BRACKETS[name]` (the shipped stage writes parentheses)."""
    left, right = BRACKETS[name]
    saved = stages._ANGLES
    stages._ANGLES = str.maketrans(dict.fromkeys(stages._LEFT_ANGLES, left) | dict.fromkeys(stages._RIGHT_ANGLES, right))
    try:
        yield
    finally:
        stages._ANGLES = saved


def units() -> list[dict]:
    """One unit per question asked of the classifier: {id, group, label, prompts: [rendered prompt, ...]}."""
    out, stage = [], LlamaGuard()
    for row in sh.held_back(DATA_ROOT):
        text = MARKUP(row["prompt"])
        for name in BRACKETS:
            with brackets(name):
                out.append({"id": f"{row['id']}::markup::{name}", "group": f"markup/{name}", "label": row["label"],
                            "prompts": sh.hardened_prompts(text, stage)})
    by_sentence = LlamaGuard(sentences=True)
    rows = sorted(experiments._load("ifeval", DATA_ROOT), key=lambda r: r["id"])[:N_SENTENCES]
    for row in rows:
        whole = sh.hardened_prompts(row["prompt"], stage)
        every = sh.hardened_prompts(row["prompt"], by_sentence)
        out.append({"id": f"{row['id']}::whole", "group": "ifeval/whole", "label": "safe", "prompts": whole})
        out.append({"id": f"{row['id']}::sentences", "group": "ifeval/sentences", "label": "safe", "prompts": every})
    return out


def replay() -> dict:
    """Dilution and hidden text on the study's 200 unsafe prompts, from its recorded replies: how many the shipped
    stage flags by default and with `sentences=True`. None when a prompt has no recorded reply."""
    study = _study()
    replies = {r["prompt_sha256"]: r["output"] for r in study._jsonl(STUDY_RAW)}
    out = {}
    for form in ("benign_suffix", "tag_hidden"):
        for name, stage in (("default", LlamaGuard()), ("sentences", LlamaGuard(sentences=True))):
            flagged = missing = 0
            for row in sh.held_back(DATA_ROOT):
                if row["label"] != "unsafe":
                    continue
                keys = [_sha(p) for p in sh.hardened_prompts(sh.ATTACKS[form](row["prompt"]), stage)]
                if any(parse_verdict(replies[k])["label"] == "unsafe" for k in keys if k in replies):
                    flagged += 1
                elif any(k not in replies for k in keys):
                    missing += 1
            out[f"{form}/{name}"] = {"flagged": flagged, "undetermined": missing}
    return out


def table(all_units: list[dict], records: list[dict]) -> str:
    replies = {r["prompt_sha256"]: r["output"] for r in records}
    lines = []
    for group in dict.fromkeys(u["group"] for u in all_units):
        for label in ("unsafe", "safe"):
            rows = [u for u in all_units if u["group"] == group and u["label"] == label]
            done = [u for u in rows if all(_sha(p) in replies for p in u["prompts"])]
            if not rows:
                continue
            flagged = sum(any(parse_verdict(replies[_sha(p)])["label"] != "safe" for p in u["prompts"]) for u in done)
            calls = sum(len(u["prompts"]) for u in rows)
            lines.append(f"  {group:18} {label:6} flagged {flagged:3} of {len(done):3} answered ({len(rows)} units, "
                         f"{calls} calls)")
    return "\n".join(lines)


def cmd_plan(a) -> int:
    all_units = units()
    done = {r["prompt_sha256"] for r in _study()._jsonl(PILOT)}
    todo = {_sha(p) for u in all_units for p in u["prompts"]}
    print(f"units: {len(all_units)}; distinct prompts: {len(todo)}; recorded: {len(todo & done)}")
    print(f"replay (no call): {json.dumps(replay())}")
    return 0


def cmd_pilot(a, transport) -> int:
    study = _study()
    lg3 = study._lg3()
    digest = study._ready(transport)
    all_units = units()
    done = {r["prompt_sha256"] for r in study._jsonl(PILOT)}
    asked = 0
    for unit in all_units:
        for prompt in unit["prompts"]:
            key = _sha(prompt)
            if key in done:
                continue
            start = time.perf_counter()
            output = lg3.ask(transport, LLAMA_GUARD_MODEL, prompt)
            study._append(PILOT, {"unit": unit["id"], "prompt_sha256": key, "output": output,
                                  "lg_model": LLAMA_GUARD_MODEL, "digest": digest,
                                  "seconds": round(time.perf_counter() - start, 2)})
            done.add(key)
            asked += 1
    print(f"pilot (development, seen prompts, never quoted): {asked} new replies\n"
          f"{table(all_units, study._jsonl(PILOT))}\nreplay: {json.dumps(replay())}")
    return 0


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("pilot")
    a = parser.parse_args(argv)
    if a.cmd == "pilot":
        return cmd_pilot(a, transport or _study()._lg3().http_transport())
    return cmd_plan(a)


if __name__ == "__main__":
    raise SystemExit(main())
