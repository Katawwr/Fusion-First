"""Development pilot for three weaknesses the stage-hardening study showed (2026-11-14): the stage wrongly flags
more safe prompts that carry markup; a harmless question appended to a request halves detection; a request hidden
in tag characters is caught half the time. Seen prompts only, never quoted. Dev-only; local Ollama only; no spend.

    python scripts/stage_pieces.py plan     # the size of the Ollama job
    python scripts/stage_pieces.py pilot    # ONE Ollama job, resumable; prints the table
    python scripts/stage_pieces.py pilot2   # the follow-up: line breaks (the first pilot cleared the brackets)

Three questions:
- markup: which way of writing an angle bracket costs least? The 400 prompts of the stage-hardening study (now
  seen) with the markup suffix, rendered with brackets as ( ), as [ ] and as spaces.
- sentences: what does `LlamaGuard(sentences=True)` cost on ordinary multi-sentence text? The first IFEval prompts,
  whole and sentence by sentence.
- dilution and hidden text: replayed from the study's recorded replies, no call (`replay`).

`pilot2` asks what the first left open: the bracket rendering did not move the markup cost, so is it the one-line
flattening? The same 400 prompts flat with the brackets kept, and with line breaks kept (one newline) or written
as " / "; and the forged-structure attacks under both, since the flattening is there to defeat them.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import pathlib
import re
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
LINES = {"flat": " ", "newline": "\n", "slash": " / "}  # what a run of line breaks becomes ("flat" ships)
PILOT2 = (("flat", "angle"), ("newline", "paren"), ("slash", "paren"))
STRUCTURE = ("forged_turn", "fake_delimiter", "variant_turn", "variant_delimiter")
ANGLE = ("<", ">")


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


class _Breaks:
    """Stands in for the stage's line-break pattern: each run of line breaks becomes `to`, whatever is asked."""

    def __init__(self, pattern, to: str):
        self.runs, self.to = re.compile(f"(?:{pattern.pattern})+"), to

    def sub(self, _repl, text: str) -> str:
        return self.runs.sub(lambda _m: self.to, text)


@contextlib.contextmanager
def rendering(line: str, bracket: str):
    """The stage with line breaks written as `LINES[line]` and angle brackets as `bracket` ("angle" keeps them)."""
    saved = stages._LINE_BREAK, stages._ANGLES
    left, right = ANGLE if bracket == "angle" else BRACKETS[bracket]
    if line != "flat":
        stages._LINE_BREAK = _Breaks(saved[0], LINES[line])
    stages._ANGLES = str.maketrans(dict.fromkeys(stages._LEFT_ANGLES, left) | dict.fromkeys(stages._RIGHT_ANGLES, right))
    try:
        yield
    finally:
        stages._LINE_BREAK, stages._ANGLES = saved


def units2(structure: tuple[str, ...] = ()) -> list[dict]:
    """The follow-up's units: the markup prompts under each rendering of `PILOT2`, and the forged-structure attacks
    on the unsafe prompts under each line rendering named in `structure` (asked only for one that helps)."""
    out, stage = [], LlamaGuard()
    for row in sh.held_back(DATA_ROOT):
        for line, bracket in PILOT2:
            with rendering(line, bracket):
                out.append({"id": f"{row['id']}::markup::{line}-{bracket}", "group": f"markup/{line}-{bracket}",
                            "label": row["label"], "prompts": sh.hardened_prompts(MARKUP(row["prompt"]), stage)})
                if line not in structure or row["label"] != "unsafe":
                    continue
                for form in STRUCTURE:
                    out.append({"id": f"{row['id']}::{form}::{line}", "group": f"{form}/{line}", "label": "unsafe",
                                "prompts": sh.hardened_prompts(sh.ATTACKS[form](row["prompt"]), stage)})
    return out


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
    study = _study()
    raw = study._jsonl(STUDY_RAW)
    for name, make, known in (("pilot", units, []), ("pilot2", units2, raw),
                              ("pilot2 --structure newline slash", lambda: units2(("newline", "slash")), raw)):
        all_units = make()
        done = {r["prompt_sha256"] for r in study._jsonl(PILOT) + known}
        todo = {_sha(p) for u in all_units for p in u["prompts"]}
        print(f"{name}: units {len(all_units)}; distinct prompts {len(todo)}; recorded {len(todo & done)}; "
              f"to ask {len(todo - done)}")
    print(f"replay (no call): {json.dumps(replay())}")
    return 0


def cmd_pilot(a, transport, make=None) -> int:
    study = _study()
    lg3 = study._lg3()
    digest = study._ready(transport)
    all_units = (make or units)()
    known = study._jsonl(STUDY_RAW) if make else []  # a prompt the study already asked is not re-asked
    done = {r["prompt_sha256"] for r in study._jsonl(PILOT) + known}
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
          f"{table(all_units, study._jsonl(PILOT) + known)}\nreplay: {json.dumps(replay())}")
    return 0


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("pilot")
    sub.add_parser("pilot2").add_argument("--structure", nargs="*", default=[], choices=["newline", "slash"])
    a = parser.parse_args(argv)
    if a.cmd in ("pilot", "pilot2"):
        make = (lambda: units2(tuple(a.structure))) if a.cmd == "pilot2" else None
        return cmd_pilot(a, transport or _study()._lg3().http_transport(), make)
    return cmd_plan(a)


if __name__ == "__main__":
    raise SystemExit(main())
