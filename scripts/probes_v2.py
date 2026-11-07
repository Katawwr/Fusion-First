"""Validate and id the v2 probe corpus (`datasets/probes/<check>.v2.jsonl`). Dev-only: not packaged.

    python scripts/probes_v2.py assign-ids datasets/probes/excessive_agency.v2.jsonl
    python scripts/probes_v2.py check datasets/probes/excessive_agency.v2.jsonl datasets/probes/data_exfiltration.v2.jsonl

`assign-ids` rewrites every row's `id` to the content hash (`fusion_first.attacks.templates.probe_row_id`;
idempotent). `check` exits 1 and lists every problem: the per-row contract enforced by the template loader,
plus the corpus rules (size, technique coverage, the Quick prefix, oracle sanity, duplicates, provenance).
The file name gives the check: `<check>.v2.jsonl`.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fusion_first.attacks.templates import (  # noqa: E402
    QUICK_TEMPLATES_PER_CHECK,
    V2_ID_PREFIX,
    _validate_v2_row,
    probe_row_id,
)
from fusion_first.schemas import Role, Step, ToolCall, Trajectory  # noqa: E402
from fusion_first.validate.oracles import _hosts_in, action_oracle  # noqa: E402

MIN_ROWS = 30
MIN_TECHNIQUES = 5  # attack techniques with at least MIN_PER_TECHNIQUE rows
MIN_PER_TECHNIQUE = 3
MIN_BENIGN = 3
QUICK_MIN_TECHNIQUES = 4
TECHNIQUE_ORDER = ("direct_instruction", "authority_pretext", "delegated_source", "payload_split",
                   "multilingual", "encoded", "benign_control")


def load_rows(path: pathlib.Path) -> list[dict]:
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            rows.append(json.loads(line))
    return rows


def write_rows(path: pathlib.Path, rows: list[dict]) -> None:
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    pathlib.Path(path).write_bytes(text.encode("utf-8"))


def check_of(path: pathlib.Path) -> str:
    name = pathlib.Path(path).name
    if not name.endswith(".v2.jsonl"):
        raise SystemExit(f"{path}: expected a <check>.v2.jsonl file")
    check = name[: -len(".v2.jsonl")]
    if check not in V2_ID_PREFIX:
        raise SystemExit(f"{path}: no v2 corpus for check {check!r} (known: {sorted(V2_ID_PREFIX)})")
    return check


def with_id(row: dict, check: str) -> dict:
    body = {k: v for k, v in row.items() if k != "id"}
    return {"id": probe_row_id(body, V2_ID_PREFIX[check]), **body}


def oracle_verdict(row: dict, calls: list[dict]) -> bool:
    """`action_oracle` (with the row's oracle spec) on a trajectory holding only these calls: True = issue."""
    traj = Trajectory(steps=[Step(role=Role.ASSISTANT, tool_call=ToolCall(name=c["tool"],
                                                                           arguments=c.get("arguments") or {}))
                             for c in calls])
    spec = row["oracle"]
    return action_oracle(traj, forbidden_tools=spec.get("forbidden_tools") or (),
                         allowlisted_domains=spec.get("allowlisted_domains") or (),
                         check_destinations=bool(spec.get("check_destinations"))).is_issue


def destinations(action: dict) -> set[str]:
    """The hosts an action's arguments name (as the action oracle reads them)."""
    return set(_hosts_in(action.get("arguments") or {}))


def dedupe_key(row: dict) -> tuple[str, tuple[str, ...]]:
    return row["user"].strip(), tuple(t["result"] for t in row["turns"] if t.get("injected"))


def _row_problems(row: dict, check: str) -> list[str]:
    rid = row.get("id", "<no id>")
    try:
        _validate_v2_row(row, check)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return [str(e) if str(e).startswith(rid) else f"{rid}: {e}"]
    out = []
    names = {t["function"]["name"] for t in row["tools"]}
    for t in row["turns"]:
        if t.get("injected") and t.get("tool") not in names:
            out.append(f"{rid}: injected turn must name a declared tool {sorted(names)}, got {t.get('tool')!r}")
    if row["technique"] != "benign_control" and not oracle_verdict(row, [row["attack_action"]]):
        out.append(f"{rid}: oracle misses attack_action {row['attack_action']}")
    benign = [{"tool": n, "arguments": {}} for n in row["oracle"].get("benign_tools") or ()]
    if not benign:
        out.append(f"{rid}: oracle benign_tools is empty")
    elif oracle_verdict(row, benign):
        out.append(f"{rid}: oracle flags the benign_tools calls {[c['tool'] for c in benign]}")
    source = (row.get("provenance") or {}).get("source")
    if not isinstance(source, str) or not source.strip():
        out.append(f"{rid}: provenance.source is empty")
    return out


def _file_problems(path: pathlib.Path, rows: list[dict], check: str) -> list[str]:
    out = [p for r in rows for p in _row_problems(r, check)]
    if len(rows) < MIN_ROWS:
        out.append(f"{path}: {len(rows)} rows, need at least {MIN_ROWS}")
    techniques = [r.get("technique") for r in rows]
    counts = collections.Counter(t for t in techniques if t != "benign_control")
    covered = sorted(t for t, n in counts.items() if n >= MIN_PER_TECHNIQUE)
    if len(covered) < MIN_TECHNIQUES:
        out.append(f"{path}: {len(covered)} attack techniques with >= {MIN_PER_TECHNIQUE} rows {covered}, "
                   f"need {MIN_TECHNIQUES}")
    n_benign = techniques.count("benign_control")
    if n_benign < MIN_BENIGN:
        out.append(f"{path}: {n_benign} benign_control rows, need at least {MIN_BENIGN}")
    quick = techniques[:QUICK_TEMPLATES_PER_CHECK]
    if len(set(quick)) < QUICK_MIN_TECHNIQUES or quick.count("benign_control") != 1:
        out.append(f"{path}: the Quick prefix (first {QUICK_TEMPLATES_PER_CHECK} rows) must span >= "
                   f"{QUICK_MIN_TECHNIQUES} techniques with exactly one benign_control, got {quick}")
    rest = techniques[QUICK_TEMPLATES_PER_CHECK:]
    runs = [t for i, t in enumerate(rest) if i == 0 or rest[i - 1] != t]
    if len(runs) != len(set(runs)):
        out.append(f"{path}: rows after the Quick prefix must be grouped by technique, got runs {runs}")
    return out


def problems(paths: list[pathlib.Path]) -> list[str]:
    out: list[str] = []
    ids: collections.Counter[str] = collections.Counter()
    keys: collections.Counter[tuple] = collections.Counter()
    for path in paths:
        rows = load_rows(path)
        out += _file_problems(path, rows, check_of(path))
        ids.update(r.get("id", "<no id>") for r in rows)
        keys.update(dedupe_key(r) for r in rows if isinstance(r.get("user"), str) and isinstance(r.get("turns"), list))
    out += [f"id {i} appears more than once" for i, n in ids.items() if n > 1]
    out += [f"duplicate user + injected text: {k[0][:60]!r}" for k, n in keys.items() if n > 1]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "assign-ids"):
        sub.add_parser(name).add_argument("files", nargs="+", type=pathlib.Path)
    args = ap.parse_args(argv)
    if args.cmd == "assign-ids":
        for path in args.files:
            check = check_of(path)
            rows = [with_id(r, check) for r in load_rows(path)]
            write_rows(path, rows)
            print(f"{path}: {len(rows)} ids assigned")
        return 0
    found = problems(args.files)
    for p in found:
        print(f"FAIL {p}")
    if found:
        print(f"{len(found)} problem(s)")
        return 1
    print(f"ok: {', '.join(str(p) for p in args.files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
