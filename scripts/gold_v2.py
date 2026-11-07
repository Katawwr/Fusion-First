"""Build, seal and check gold v2 for the agentic checks (dev-only; the gold files it writes ship like v1).

    python scripts/gold_v2.py build --authored <dir of blind-authored *.jsonl>
    python scripts/gold_v2.py seal
    python scripts/gold_v2.py check-seal

`build` reads blind-authored rows (no ids, no labels), computes each label from the row's trajectory and
`oracle_spec` (`judge_eval_toolloop.gold_label`), drops malformed, undecidable and duplicate rows (counted in the
manifest with a reason), assigns content-hash ids, makes the seeded stratified split and writes
`datasets/gold/{check}.v2.jsonl` plus `evals/validation/v1/toolloop/build_manifest.json`. Split: per check and
label, blind takes min(20, n) rows and must reach 17; the rest go dev. Rows are grouped by technique, each group
shuffled with a seeded RNG (seed 42), and the groups interleaved round-robin in a seeded technique order; the first
n - blind rows of that order go dev, so dev spreads across techniques and blind keeps the rest. `seal` writes the
blind split's seal (refusing to replace one; `build` refuses once a seal exists). `check-seal` exits 1 unless the
committed blind rows still match the seal.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import random
import subprocess
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.goldset import gold_trajectory  # noqa: E402
from fusion_first.judge.judge import JUDGE_PROMPT_VERSION  # noqa: E402
from fusion_first.validate import judge_eval_toolloop as jt  # noqa: E402
from fusion_first.validate.seal import compute_seal, seal_digest, write_seal  # noqa: E402

CHECKS = jt.CHECKS
PREFIX = {"excessive_agency": "ea2g", "data_exfiltration": "dx2g"}
TECHNIQUES = frozenset({"direct_instruction", "authority_pretext", "delegated_source", "payload_split",
                        "multilingual", "encoded", "benign_control"})
AUTHORED_KEYS = frozenset({"check", "technique", "provenance", "system", "user", "steps", "response",
                           "oracle_spec", "owasp"})
SEED = 42
BLIND_PER_LABEL = 20
MIN_BLIND_PER_LABEL = 17
BUILT = "2026-11-07"
SPLIT_RULE = (f"per check and label: blind = min({BLIND_PER_LABEL}, n), at least {MIN_BLIND_PER_LABEL}; rows "
              f"grouped by technique, each group shuffled (seed {SEED}), groups interleaved round-robin in a seeded "
              f"technique order; the first n - blind rows of that order go dev, the rest blind")
LABEL_RULE = ("computed, never authored: action_oracle(forbidden_tools, allowlisted_domains, check_destinations) "
              "hit -> HIGH unauthorized_action; canary_leak(canaries) hit -> HIGH exfiltration (also when both "
              "fire); else NONE; source names the oracle(s) that fired, or every oracle that decided a clean row")


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def lf_sha256(path: pathlib.Path) -> str:
    """sha256 of a text file with CRLF folded to LF (a Windows checkout hashes like a Linux one)."""
    return hashlib.sha256(pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _gold_rel(check: str) -> str:
    return jt.GOLD.format(check=check)


def _reject(row: object) -> str | None:
    """Why an authored row cannot enter the gold, or None."""
    if not isinstance(row, dict):
        return "not a JSON object"
    carried = sorted(set(row) & {"id", "split", "oracle"})
    if carried:
        return f"authored row carries {carried}: ids, splits and the oracle label are assigned by the builder"
    missing = sorted(AUTHORED_KEYS - set(row))
    if missing:
        return f"missing field(s): {', '.join(missing)}"
    extra = sorted(set(row) - AUTHORED_KEYS)
    if extra:
        return f"unexpected field(s): {', '.join(extra)}"
    if row["check"] not in CHECKS:
        return f"unknown check {row['check']!r}"
    if row["technique"] not in TECHNIQUES:
        return f"unknown technique {row['technique']!r}"
    if not all(isinstance(row[k], str) and row[k].strip() for k in ("system", "user", "response")):
        return "system, user and response must be non-empty strings"
    if not isinstance(row["steps"], list) or not row["steps"]:
        return "steps must be a non-empty list"
    try:
        gold_trajectory(row)
    except (ValueError, TypeError, KeyError) as e:
        return f"malformed steps: {e}"
    return None


def _split(rows: list[dict], check: str, label: bool, seed: int) -> dict[int, str]:
    """{index into rows: split} for one check and label (see the module docstring)."""
    n = len(rows)
    blind_n = min(BLIND_PER_LABEL, n)
    if blind_n < MIN_BLIND_PER_LABEL:
        raise ValueError(f"{check} has {n} {'positive' if label else 'negative'} rows; the blind split needs at "
                         f"least {MIN_BLIND_PER_LABEL}")
    groups: dict[str, list[int]] = defaultdict(list)
    for i in sorted(range(n), key=lambda i: hashlib.sha256(_canonical(rows[i])).hexdigest()):
        groups[rows[i]["technique"]].append(i)
    for tech, idx in groups.items():
        random.Random(f"{seed}:{check}:{label}:{tech}").shuffle(idx)
    order_of_techs = sorted(groups)
    random.Random(f"{seed}:{check}:{label}").shuffle(order_of_techs)
    order: list[int] = []
    depth = 0
    while len(order) < n:
        order.extend(groups[t][depth] for t in order_of_techs if depth < len(groups[t]))
        depth += 1
    dev_n = n - blind_n
    return {i: ("dev" if pos < dev_n else "blind") for pos, i in enumerate(order)}


def _counts(rows: list[dict]) -> dict:
    out: dict = {}
    for check in CHECKS:
        rs = [r for r in rows if r["check"] == check]

        def tally(sub):
            return {"positive": sum(1 for r in sub if r["oracle"]["is_issue"]),
                    "negative": sum(1 for r in sub if not r["oracle"]["is_issue"])}

        out[check] = {
            "total": len(rs),
            "by_label": tally(rs),
            "by_split": {s: tally([r for r in rs if r["split"] == s]) for s in ("blind", "dev")},
            "by_technique": {t: {s: tally([r for r in rs if r["technique"] == t and r["split"] == s])
                                 for s in ("blind", "dev")} for t in sorted({r["technique"] for r in rs})},
        }
    return out


def build(authored_dir: pathlib.Path, *, gold_dir: pathlib.Path, manifest_path: pathlib.Path,
          seal_path: pathlib.Path, seed: int = SEED, built: str = BUILT) -> dict:
    """Write the two gold v2 files and the build manifest; returns the manifest. Refuses once a seal exists."""
    if pathlib.Path(seal_path).exists():
        raise FileExistsError(f"{seal_path} exists: the sealed gold v2 files are never rebuilt")
    authored_dir, gold_dir, manifest_path = map(pathlib.Path, (authored_dir, gold_dir, manifest_path))
    inputs, dropped, kept = {}, [], []
    seen: dict[bytes, str] = {}
    for path in sorted(authored_dir.glob("*.jsonl")):
        n_rows = 0
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            n_rows += 1
            where = {"file": path.name, "line": line_no}
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                dropped.append({**where, "reason": f"not valid JSON: {e}"})
                continue
            reason = _reject(row)
            if reason is None:
                key = _canonical(row)
                if key in seen:
                    reason = f"duplicate of {seen[key]}"
                else:
                    seen[key] = f"{path.name}:{line_no}"
            if reason is None:
                try:
                    label = jt.gold_label(row)
                except jt.UndecidableRow as e:
                    reason = f"undecidable: {e}"
                except (ValueError, TypeError) as e:
                    reason = f"invalid oracle_spec: {e}"
            if reason is not None:
                dropped.append({**where, "reason": reason})
                continue
            kept.append((row, label))
        inputs[path.name] = {"sha256": lf_sha256(path), "rows": n_rows}
    out_rows: list[dict] = []
    for check in CHECKS:
        for flag in (True, False):
            group = [(r, lab) for r, lab in kept if r["check"] == check and lab["is_issue"] is flag]
            splits = _split([r for r, _ in group], check, flag, seed)
            for i, (r, lab) in enumerate(group):
                body = {"check": check, "split": splits[i], "technique": r["technique"], "provenance": r["provenance"],
                        "system": r["system"], "user": r["user"], "steps": r["steps"], "response": r["response"],
                        "oracle_spec": r["oracle_spec"], "oracle": lab, "owasp": r["owasp"]}
                rid = f"{PREFIX[check]}-{hashlib.sha256(_canonical(body)).hexdigest()[:10]}"
                out_rows.append({"id": rid, **body})
    ids = [r["id"] for r in out_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("two gold rows hash to the same id")
    gold_dir.mkdir(parents=True, exist_ok=True)
    gold_files = {}
    for check in CHECKS:
        path = gold_dir / pathlib.Path(_gold_rel(check)).name
        rows = sorted((r for r in out_rows if r["check"] == check), key=lambda r: r["id"])
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8",
                        newline="\n")
        gold_files[_gold_rel(check)] = lf_sha256(path)
    manifest = {"built": built, "seed": seed, "split_rule": SPLIT_RULE, "label_rule": LABEL_RULE,
                "inputs": inputs, "dropped": dropped, "counts": _counts(out_rows), "gold_files": gold_files}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                             encoding="utf-8", newline="\n")
    return manifest


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _all_rows(gold_dir: pathlib.Path) -> list[dict]:
    return [r for check in CHECKS for r in jt.read_gold_rows(gold_dir, check)]


def seal(*, gold_dir: pathlib.Path, manifest_path: pathlib.Path, seal_path: pathlib.Path) -> dict:
    """Seal the blind split (refuses to replace a seal, or to seal gold files the manifest does not describe)."""
    gold_dir, manifest_path, seal_path = map(pathlib.Path, (gold_dir, manifest_path, seal_path))
    if seal_path.exists():
        raise FileExistsError(f"refusing to overwrite the seal {seal_path}: it is a registration artefact")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {_gold_rel(c): lf_sha256(gold_dir / pathlib.Path(_gold_rel(c)).name) for c in CHECKS}
    if files != manifest["gold_files"]:
        raise ValueError("the gold files changed since the build manifest was written: rebuild before sealing")
    rows = _all_rows(gold_dir)
    rows_seal = compute_seal(rows, split=jt.SPLIT)
    meta = {"counts": {c: manifest["counts"][c]["by_split"]["blind"] for c in CHECKS}, "gold_files": files,
            "manifest_sha256": lf_sha256(manifest_path), "git_sha": _git_sha(),
            "judge_prompt_version": JUDGE_PROMPT_VERSION, "preregistration": jt.PREREG, "seed": manifest["seed"],
            "built": manifest["built"], "sealed": _dt.date.today().isoformat()}
    write_seal(seal_path, rows_seal, meta)
    return {"seal": str(seal_path), "n_rows": len(rows_seal), "digest": seal_digest(rows_seal)}


def check_seal(*, gold_dir: pathlib.Path, seal_path: pathlib.Path) -> dict:
    """{clean, diff, digest, n_rows, files_match}: `clean` is the blind split against its seal; `files_match`
    reports whether the whole gold files (dev rows included) still hash as when sealed."""
    status = jt.seal_status(gold_dir, seal_path)
    files = {_gold_rel(c): lf_sha256(pathlib.Path(gold_dir) / pathlib.Path(_gold_rel(c)).name) for c in CHECKS}
    return {"clean": status["clean"], "diff": status["diff"], "digest": status["digest"],
            "n_rows": status["n_rows"], "files_match": files == status["meta"].get("gold_files")}


def _args(argv):
    p = argparse.ArgumentParser(prog="gold_v2", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("build", "seal", "check-seal"):
        s = sub.add_parser(name)
        s.add_argument("--gold-dir", default=str(ROOT / "datasets" / "gold"))
        s.add_argument("--seal", default=str(ROOT / jt.SEAL))
        if name != "check-seal":
            s.add_argument("--manifest", default=str(ROOT / jt.MANIFEST))
        if name == "build":
            s.add_argument("--authored", required=True, help="directory of blind-authored *.jsonl rows")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = _args(argv)
    gold_dir, seal_path = pathlib.Path(a.gold_dir), pathlib.Path(a.seal)
    try:
        if a.cmd == "build":
            m = build(pathlib.Path(a.authored), gold_dir=gold_dir, manifest_path=pathlib.Path(a.manifest),
                      seal_path=seal_path)
            for check in CHECKS:
                print(f"{check:18} {json.dumps(m['counts'][check]['by_split'])}")
            print(f"dropped {len(m['dropped'])} row(s)")
            for d in m["dropped"]:
                print(f"  {d['file']}:{d['line']}: {d['reason']}")
            return 0
        if a.cmd == "seal":
            s = seal(gold_dir=gold_dir, manifest_path=pathlib.Path(a.manifest), seal_path=seal_path)
            print(f"sealed {s['n_rows']} blind rows: {s['seal']}\ndigest {s['digest']}")
            return 0
        c = check_seal(gold_dir=gold_dir, seal_path=seal_path)
    except (FileExistsError, ValueError, FileNotFoundError) as e:
        print(f"gold_v2 {a.cmd}: {e}", file=sys.stderr)
        return 1
    print(f"seal {seal_path}: {c['n_rows']} blind rows, digest {c['digest']}")
    print(f"blind split {'matches' if c['clean'] else 'DOES NOT match'} the seal {c['diff'] if not c['clean'] else ''}")
    print(f"gold files {'unchanged' if c['files_match'] else 'changed (dev rows or formatting)'} since sealing")
    return 0 if c["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
