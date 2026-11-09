"""Build, seal and check a sealed gold set for a `Study` (dev-only; the gold files it writes ship like gold v1).

`build` reads blind-authored rows (no ids, no labels), computes each label from the row's trajectory and
`oracle_spec` with the study's oracles (`judge_eval_toolloop.gold_label`), drops malformed, undecidable and duplicate
rows (counted in the manifest with a reason), assigns content-hash ids, makes the seeded split and writes the study's
gold files plus its build manifest. Split, per check and label: with `study.blind_per_label` set, blind takes
min(blind_per_label, n) rows and must reach `study.min_blind_per_label`; rows are grouped by technique, each group
shuffled with a seeded RNG, the groups interleaved round-robin in a seeded technique order, and the first n - blind
rows of that order go dev. With it unset, every row is blind and n must still reach `min_blind_per_label`. A study
with `patterns` also needs `min_blind_per_pattern` blind positives and blind negatives per pattern a check carries.
`seal` writes the blind split's seal (refusing to replace one; `build` refuses once a seal exists). `check_seal`
reports whether the committed blind rows still match the seal.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import random
import subprocess
from collections import defaultdict

from fusion_first.goldset import gold_trajectory
from fusion_first.validate import judge_eval_toolloop as jt
from fusion_first.validate.seal import compute_seal, seal_digest, write_seal

AUTHORED_KEYS = frozenset({"check", "technique", "provenance", "system", "user", "steps", "response",
                           "oracle_spec", "owasp"})
SEED = 42


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def lf_sha256(path: pathlib.Path) -> str:
    """sha256 of a text file with CRLF folded to LF (a Windows checkout hashes like a Linux one)."""
    return hashlib.sha256(pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def reject(row: object, study: jt.Study) -> str | None:
    """Why an authored row cannot enter the study's gold, or None."""
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
    if row["check"] not in study.checks:
        return f"unknown check {row['check']!r}"
    if row["technique"] not in study.techniques:
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


def split(rows: list[dict], check: str, label: bool, seed: int, study: jt.Study) -> dict[int, str]:
    """{index into rows: split} for one check and label (see the module docstring)."""
    n = len(rows)
    blind_n = n if study.blind_per_label is None else min(study.blind_per_label, n)
    if blind_n < study.min_blind_per_label:
        raise ValueError(f"{check} has {n} {'positive' if label else 'negative'} rows; the blind split needs at "
                         f"least {study.min_blind_per_label}")
    if blind_n == n:
        return dict.fromkeys(range(n), "blind")
    groups: dict[str, list[int]] = defaultdict(list)
    for i in sorted(range(n), key=lambda i: hashlib.sha256(canonical(rows[i])).hexdigest()):
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


def _tally(sub) -> dict:
    return {"positive": sum(1 for r in sub if r["oracle"]["is_issue"]),
            "negative": sum(1 for r in sub if not r["oracle"]["is_issue"])}


def counts(rows: list[dict], study: jt.Study) -> dict:
    out: dict = {}
    for check in study.checks:
        rs = [r for r in rows if r["check"] == check]
        out[check] = {
            "total": len(rs),
            "by_label": _tally(rs),
            "by_split": {s: _tally([r for r in rs if r["split"] == s]) for s in ("blind", "dev")},
            "by_technique": {t: {s: _tally([r for r in rs if r["technique"] == t and r["split"] == s])
                                 for s in ("blind", "dev")} for t in sorted({r["technique"] for r in rs})},
        }
        if study.patterns.get(check):
            out[check]["by_pattern"] = {
                p: {s: _tally([r for r in rs if study.pattern_of(r["technique"]) == p and r["split"] == s])
                    for s in ("blind", "dev")} for p in study.patterns[check]}
    return out


def _pattern_floor(rows: list[dict], study: jt.Study) -> None:
    if study.min_blind_per_pattern is None:
        return
    for check, patterns in study.patterns.items():
        for pattern in patterns:
            blind = [r for r in rows if r["check"] == check and r["split"] == "blind"
                     and study.pattern_of(r["technique"]) == pattern]
            tally = _tally(blind)
            if min(tally.values()) < study.min_blind_per_pattern:
                raise ValueError(f"{check} {pattern}: {tally['positive']} blind positive(s) and {tally['negative']} "
                                 f"blind negative(s); at least {study.min_blind_per_pattern} of each are required")


def build(authored_dir: pathlib.Path, *, study: jt.Study, gold_dir: pathlib.Path, manifest_path: pathlib.Path,
          seal_path: pathlib.Path, split_rule: str | None = None, label_rule: str | None = None, seed: int = SEED,
          built: str | None = None) -> dict:
    """Write the study's gold files and build manifest; returns the manifest. Refuses once a seal exists. The
    study's command line passes the rule texts the manifest records (`split_rule`, `label_rule`)."""
    split_rule = split_rule or f"{study.name}: see scripts/gold_{study.gold_version}.py SPLIT_RULE"
    label_rule = label_rule or f"{study.name}: see scripts/gold_{study.gold_version}.py LABEL_RULE"
    if pathlib.Path(seal_path).exists():
        raise FileExistsError(f"{seal_path} exists: the sealed gold {study.gold_version} files are never rebuilt")
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
            reason = reject(row, study)
            if reason is None:
                key = canonical(row)
                if key in seen:
                    reason = f"duplicate of {seen[key]}"
                else:
                    seen[key] = f"{path.name}:{line_no}"
            if reason is None:
                try:
                    label = jt.gold_label(row, study)
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
    for check in study.checks:
        for flag in (True, False):
            group = [(r, lab) for r, lab in kept if r["check"] == check and lab["is_issue"] is flag]
            splits = split([r for r, _ in group], check, flag, seed, study)
            for i, (r, lab) in enumerate(group):
                body = {"check": check, "split": splits[i], "technique": r["technique"], "provenance": r["provenance"],
                        "system": r["system"], "user": r["user"], "steps": r["steps"], "response": r["response"],
                        "oracle_spec": r["oracle_spec"], "oracle": lab, "owasp": r["owasp"]}
                rid = f"{study.id_prefix[check]}-{hashlib.sha256(canonical(body)).hexdigest()[:10]}"
                out_rows.append({"id": rid, **body})
    ids = [r["id"] for r in out_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("two gold rows hash to the same id")
    _pattern_floor(out_rows, study)
    gold_dir.mkdir(parents=True, exist_ok=True)
    gold_files = {}
    for check in study.checks:
        path = study.gold_path(gold_dir, check)
        rows = sorted((r for r in out_rows if r["check"] == check), key=lambda r: r["id"])
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8",
                        newline="\n")
        gold_files[study.gold.format(check=check)] = lf_sha256(path)
    manifest = {"built": built or _dt.date.today().isoformat(), "seed": seed, "split_rule": split_rule,
                "label_rule": label_rule, "inputs": inputs, "dropped": dropped, "counts": counts(out_rows, study),
                "gold_files": gold_files}
    if not study.legacy_envelope:
        manifest.update({"study": study.name, "judge_prompt_version": study.judge_prompt_version})
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                             encoding="utf-8", newline="\n")
    return manifest


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=jt.ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def seal(*, study: jt.Study, gold_dir: pathlib.Path, manifest_path: pathlib.Path, seal_path: pathlib.Path) -> dict:
    """Seal the blind split (refuses to replace a seal, or to seal gold files the manifest does not describe)."""
    gold_dir, manifest_path, seal_path = map(pathlib.Path, (gold_dir, manifest_path, seal_path))
    if seal_path.exists():
        raise FileExistsError(f"refusing to overwrite the seal {seal_path}: it is a registration artefact")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {study.gold.format(check=c): lf_sha256(study.gold_path(gold_dir, c)) for c in study.checks}
    if files != manifest["gold_files"]:
        raise ValueError("the gold files changed since the build manifest was written: rebuild before sealing")
    rows = [r for check in study.checks for r in jt.read_gold_rows(gold_dir, check, study)]
    rows_seal = compute_seal(rows, split=study.split)
    meta = {"counts": {c: manifest["counts"][c]["by_split"]["blind"] for c in study.checks}, "gold_files": files,
            "manifest_sha256": lf_sha256(manifest_path), "git_sha": _git_sha(),
            "judge_prompt_version": study.judge_prompt_version, "preregistration": study.prereg,
            "seed": manifest["seed"], "built": manifest["built"], "sealed": _dt.date.today().isoformat()}
    if not study.legacy_envelope:
        meta["study"] = study.name
    write_seal(seal_path, rows_seal, meta)
    return {"seal": str(seal_path), "n_rows": len(rows_seal), "digest": seal_digest(rows_seal)}


def check_seal(*, study: jt.Study, gold_dir: pathlib.Path, seal_path: pathlib.Path) -> dict:
    """{clean, diff, digest, n_rows, files_match}: `clean` is the blind split against its seal; `files_match`
    reports whether the whole gold files (dev rows included) still hash as when sealed."""
    status = jt.seal_status(gold_dir, seal_path, study)
    files = {study.gold.format(check=c): lf_sha256(study.gold_path(gold_dir, c)) for c in study.checks}
    return {"clean": status["clean"], "diff": status["diff"], "digest": status["digest"],
            "n_rows": status["n_rows"], "files_match": files == status["meta"].get("gold_files")}
