"""Step 5: request binding by verb class, scored on sealed blind-authored rows. Pre-registered in
evals/validation/v1/PREREG_step5_binding.md. No model runs: the guard is deterministic.

    python scripts/step5_binding.py build     # authored files + the checker's answers -> rows + seal (before the PREREG commit)
    python scripts/step5_binding.py score     # verifies the seal and the rule commits; writes the evidence once

Each arm is the guard as committed: `fusion_first/` is extracted from the arm's commit into a temporary folder and
run in its own interpreter, so neither arm can see the working tree.
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.stats.metrics import wilson_interval  # noqa: E402
from fusion_first.stats.paired import mcnemar_exact_p, paired_bootstrap_diff  # noqa: E402
from fusion_first.validate.prereg import binding_decision  # noqa: E402
from fusion_first.validate.seal import (  # noqa: E402
    compute_seal,
    load_seal,
    verify_seal,
    write_seal,
)

# Registered (PREREG_step5_binding.md); changing any of these after registration voids the run.
OLD_SHA = "e056d77945bb01c94f07145928fbd0561f35e565"  # the published rules
NEW_SHA = "4442d6a94b152820a265d78883ba36614aaac7b1"  # request binding by verb class
RULE_PATHS = ("fusion_first/guardrail",)
PREREG = "evals/validation/v1/PREREG_step5_binding.md"
DATA = ROOT / "datasets/guard_step5"
AUTHORED = DATA / "authored"
CHECKS = DATA / "checks.json"
ROWS = DATA / "rows.v1.jsonl"
SEAL = DATA / "rows.v1.seal.json"
OUT = ROOT / "evals/validation/v1/step5_binding.json"
LABELS = ("legitimate", "hijack")
N_BOOT, SEED = 10_000, 42

_ADDRESS = re.compile(r"[\w.+\-]+@[\w.\-]+\.\w+|https?://|\b(?:\d{1,3}\.){3}\d{1,3}\b", re.I)

# Runs inside the extracted commit: one guard per row, the configuration the registration fixes.
ARM = r'''
import json, os, sys
import fusion_first
assert os.path.realpath(fusion_first.__file__).startswith(os.path.realpath(os.getcwd())), fusion_first.__file__
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import GuardConfig
out = {}
for r in json.load(sys.stdin):
    guard = Guardrail(GuardConfig(require_authorization=True, allowlisted_domains=[r["org_domain"]]))
    o = guard.guard_tool_call(r["call"]["name"], r["call"]["arguments"], user_request=r["user_request"],
                              untrusted_context=True, untrusted_text=r["tool_results"])
    out[r["id"]] = {"blocked": bool(o.blocked), "rules": [e.detail for e in o.events]}
json.dump(out, sys.stdout)
'''


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def binding_only(call: dict) -> bool:
    """The call names no email address, URL or IP anywhere in its arguments: only request binding can stop it."""
    return not _ADDRESS.search(json.dumps(call.get("arguments"), ensure_ascii=False))


# ------------------------------------------------------------------------------------------------ build
def build_rows(authored: list[dict], answers: dict[str, str]) -> tuple[list[dict], dict[str, int]]:
    """Rows from the authors' files under the registered drop rule: a legitimate row the blind checker answered
    "no" (the request does not ask for this call) or a hijack row it answered "yes" is dropped; nothing else is."""
    rows, dropped = [], dict.fromkeys(LABELS, 0)
    for doc in sorted(authored, key=lambda d: d["author"]):
        for i, r in enumerate(doc["rows"]):
            rid = f"{doc['author']}-{i:03d}"
            if r["label"] not in LABELS:
                raise SystemExit(f"{rid}: unknown label {r['label']!r}")
            answer = answers.get(rid)
            if answer not in ("yes", "no"):
                raise SystemExit(f"{rid}: the validity check has no yes/no answer for this row")
            if (r["label"] == "legitimate") != (answer == "yes"):
                dropped[r["label"]] += 1
                continue
            call = {"name": r["call"]["name"], "arguments": r["call"].get("arguments") or {}}
            rows.append({"id": rid, "split": "blind", "label": r["label"], "author": doc["author"],
                         "domain": doc["domain"], "org_domain": doc["org_domain"],
                         "user_request": r["user_request"], "tool_results": r["tool_results"], "call": call,
                         "binding_only": binding_only(call)})
    return rows, dropped


def cmd_build() -> int:
    if ROWS.exists() or SEAL.exists():
        raise SystemExit(f"{ROWS.name} or its seal exists: the rows are built once")
    authored = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(AUTHORED.glob("*.json"))]
    rows, dropped = build_rows(authored, json.loads(CHECKS.read_text(encoding="utf-8")))
    ROWS.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")
    counts = collections.Counter(r["label"] for r in rows)
    write_seal(SEAL, compute_seal(rows), meta={
        "study": "guard step 5: request binding", "authors": len(authored), "rows": dict(counts),
        "dropped_by_validity_check": dropped,
        "binding_only_hijack": sum(r["binding_only"] for r in rows if r["label"] == "hijack")})
    print(json.dumps({"rows": dict(counts), "dropped": dropped}, indent=1))
    return 0


# ------------------------------------------------------------------------------------------------ score
def _rate(k: int, n: int) -> dict:
    ci = wilson_interval(k, n)
    return {"k": k, "n": n, "point": ci.point, "low": ci.low, "high": ci.high}


def _block(rows: list[dict], old: dict, new: dict) -> dict:
    o = [bool(old[r["id"]]["blocked"]) for r in rows]
    n = [bool(new[r["id"]]["blocked"]) for r in rows]
    old_only = sum(1 for a, b in zip(o, n, strict=True) if a and not b)
    new_only = sum(1 for a, b in zip(o, n, strict=True) if b and not a)
    diff = paired_bootstrap_diff(n, o, n_boot=N_BOOT, seed=SEED)  # blocked share, new minus old
    return {"n": len(rows), "old": _rate(sum(o), len(rows)), "new": _rate(sum(n), len(rows)),
            "old_only": old_only, "new_only": new_only, "mcnemar_p": mcnemar_exact_p(old_only, new_only),
            "difference": {"point": diff.point, "low": diff.low, "high": diff.high}}


def score_rows(rows: list[dict], old: dict, new: dict) -> dict:
    """The registered statistics from the rows and each arm's per-row decision ({id: {blocked, rules}})."""
    by = {label: [r for r in rows if r["label"] == label] for label in LABELS}
    domains = sorted({r["domain"] for r in rows})
    return {
        "legitimate": _block(by["legitimate"], old, new),
        "hijack": _block(by["hijack"], old, new),
        "hijack_binding_only": _block([r for r in by["hijack"] if r["binding_only"]], old, new),
        "per_domain": {
            d: {label: {"n": len(rs), "old_blocked": sum(bool(old[r["id"]]["blocked"]) for r in rs),
                        "new_blocked": sum(bool(new[r["id"]]["blocked"]) for r in rs)}
                for label in LABELS for rs in [[r for r in by[label] if r["domain"] == d]]}
            for d in domains},
    }


def decisions(sha: str, rows: list[dict]) -> dict:
    """Every row's guard decision under the rules as committed at `sha`."""
    archive = subprocess.run(["git", "archive", "--format=zip", sha, "fusion_first"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(archive)).extractall(tmp)
        env = {**os.environ, "PYTHONPATH": tmp, "PYTHONIOENCODING": "utf-8"}
        run = subprocess.run([sys.executable, "-c", ARM], cwd=tmp, env=env, input=json.dumps(rows).encode("utf-8"),
                             capture_output=True)
    if run.returncode:
        raise SystemExit(f"arm {sha[:7]} failed: {run.stderr.decode('utf-8', 'replace')[-800:]}")
    return json.loads(run.stdout.decode("utf-8"))


def cmd_score() -> int:
    if OUT.exists():
        raise SystemExit(f"{OUT.relative_to(ROOT)} exists: the sealed rows are scored once")
    if _git("status", "--porcelain", "--", *RULE_PATHS, "datasets/guard_step5", "scripts/step5_binding.py"):
        raise SystemExit("the rules, the rows or this scorer are modified in the working tree")
    if _git("diff", "--stat", NEW_SHA, "HEAD", "--", *RULE_PATHS):
        raise SystemExit(f"{RULE_PATHS} at HEAD differ from the registered new rules {NEW_SHA[:7]}")
    rows = [json.loads(x) for x in ROWS.read_text(encoding="utf-8").splitlines() if x.strip()]
    drift = verify_seal(rows, load_seal(SEAL))
    if any(drift.values()):
        raise SystemExit(f"the rows do not match their seal: {drift}")
    old, new = decisions(OLD_SHA, rows), decisions(NEW_SHA, rows)
    s = score_rows(rows, old, new)
    evidence = {"demonstration": False,
                "kind": "runtime guard, request binding by verb class: sealed blind-authored calls, old vs new rules",
                "preregistration": PREREG, "measured": _dt.date.today().isoformat(),
                "git_sha": _git("rev-parse", "HEAD"), "rules": {"old": OLD_SHA, "new": NEW_SHA},
                "seal": {"path": str(SEAL.relative_to(ROOT)).replace("\\", "/"), "n_rows": len(rows)},
                **s, "decision": binding_decision(s),
                "rows": [{"id": r["id"], "label": r["label"], "domain": r["domain"],
                          "binding_only": r["binding_only"], "old": old[r["id"]], "new": new[r["id"]]}
                         for r in rows]}
    OUT.write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: evidence[k] for k in ("legitimate", "hijack", "hijack_binding_only", "decision")}, indent=1))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="step5_binding")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("score")
    a = p.parse_args(argv)
    return cmd_build() if a.cmd == "build" else cmd_score()


if __name__ == "__main__":
    raise SystemExit(main())
