"""Build the tool-result injection detector's dataset (dev-only; offline; no model calls).

    python scripts/detector_data.py build [--out datasets/detector/v1] [--blind datasets/detector/v1/blind]
        [--agentdojo-heldout evals/validation/v1/agentdojo/heldout] [--agentdojo-dev evals/validation/v1/agentdojo/dev]
    python scripts/detector_data.py stats [--out datasets/detector/v1]
    python scripts/detector_data.py seal [--out datasets/detector/v1] [--blind datasets/detector/v1/blind]
        [--seal evals/validation/v1/detector/confirmatory.seal.json] [--force]

`build` writes dev.jsonl, confirmatory.jsonl and manifest.json; missing blind inputs are skipped and recorded in the
manifest. `seal` writes the registration's seal over confirmatory.jsonl (per-source counts, blind files, git sha,
date, frame in its meta) and refuses to replace an existing seal without --force.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate import detector_data as dd  # noqa: E402
from fusion_first.validate.seal import compute_seal, seal_digest, write_seal  # noqa: E402

OUT = ROOT / "datasets/detector/v1"
SEAL = ROOT / "evals/validation/v1/detector/confirmatory.seal.json"
PREREGISTRATION = "evals/validation/v1/PREREG_detector_v1.md"
CONFIRMATORY = "confirmatory"


def _git_sha() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return r.stdout.strip()


def _path(p: str) -> pathlib.Path:
    path = pathlib.Path(p)
    return path if path.is_absolute() else ROOT / path


def _source_counts(rows: list[dict]) -> dict:
    """{source: pos, neg, distinct_pos, distinct_neg} over the confirmatory rows themselves."""
    out: dict = {}
    for source in dd.SOURCES:
        mine = [r for r in rows if r["source"] == source]
        if mine:
            out[source] = {"pos": sum(r["label"] == 1 for r in mine), "neg": sum(r["label"] == 0 for r in mine),
                           "distinct_pos": len({r["text"] for r in mine if r["label"] == 1}),
                           "distinct_neg": len({r["text"] for r in mine if r["label"] == 0})}
    return out


def _manifest_sources(manifest: dict) -> dict:
    """The same block as `_source_counts`, read from the manifest's confirmatory counts."""
    out: dict = {}
    for source in dd.SOURCES:
        counts = manifest["counts"].get(source, {}).get(CONFIRMATORY)
        if counts:
            distinct = manifest["distinct_texts"][source][CONFIRMATORY]
            out[source] = {"pos": counts["1"], "neg": counts["0"], "distinct_pos": distinct["1"],
                           "distinct_neg": distinct["0"]}
    return out


def _blind_files(manifest: dict, blind_dir: pathlib.Path) -> dict[str, int]:
    """{blind file name: rows} for every blind input the manifest lists, each unchanged since the build."""
    inputs = manifest["blind_inputs"]
    names = ([dd.FILLERS_FILE] if inputs["fillers"] else []) + inputs["carriers"] + inputs["authors"]
    out = {}
    for name in names:
        path = blind_dir / name
        if not path.is_file():
            raise ValueError(f"blind file {path} listed in manifest.json is missing")
        if manifest["inputs"].get(dd.logical_path(path)) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"blind file {path} differs from the one manifest.json was built from")
        out[name] = len(dd.read_jsonl(path))
    return out


def seal_meta(rows: list[dict], manifest: dict, blind_dir: pathlib.Path) -> dict:
    """The seal's meta block; raises ValueError if the manifest does not describe these rows."""
    sources = _manifest_sources(manifest)
    if sources != _source_counts(rows):
        raise ValueError("manifest.json does not describe confirmatory.jsonl (per-source counts differ); rebuild")
    return {"sources": sources, "blind_files": _blind_files(manifest, blind_dir), "git_sha": _git_sha(),
            "built": _dt.date.today().isoformat(), "preregistration": PREREGISTRATION, "frame": dd.FRAME}


def seal(out: pathlib.Path, blind_dir: pathlib.Path, seal_path: pathlib.Path, force: bool = False) -> dict:
    """Write the confirmatory seal; refuses an existing seal unless `force`. Returns the printed summary."""
    if seal_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite the seal {seal_path}: it is a registration artefact "
                              "(pass --force to replace it)")
    rows = dd.read_jsonl(out / f"{CONFIRMATORY}.jsonl")
    if not rows or any(r.get("split") != CONFIRMATORY for r in rows):
        raise ValueError(f"{out / 'confirmatory.jsonl'} must hold confirmatory rows only, and at least one")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    meta = seal_meta(rows, manifest, blind_dir)
    rows_seal = compute_seal(rows, split=CONFIRMATORY)
    write_seal(seal_path, rows_seal, meta)
    return {"seal": str(seal_path), "n_rows": len(rows_seal), "digest": seal_digest(rows_seal)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build dev.jsonl, confirmatory.jsonl and manifest.json")
    b.add_argument("--out", default=str(OUT))
    b.add_argument("--blind", default=str(OUT / "blind"))
    b.add_argument("--agentdojo-heldout", default="evals/validation/v1/agentdojo/heldout")
    b.add_argument("--agentdojo-dev", default="evals/validation/v1/agentdojo/dev")
    b.add_argument("--external", default="datasets/external", help="the imported third-party sets")
    s = sub.add_parser("stats", help="print the manifest")
    s.add_argument("--out", default=str(OUT))
    z = sub.add_parser("seal", help="seal confirmatory.jsonl for the registration")
    z.add_argument("--out", default=str(OUT))
    z.add_argument("--blind", default=str(OUT / "blind"), help="the blind inputs the dataset was built from")
    z.add_argument("--seal", default=str(SEAL))
    z.add_argument("--force", action="store_true", help="replace an existing seal")
    a = ap.parse_args(argv)

    out = _path(a.out)
    if a.cmd == "stats":
        print((out / "manifest.json").read_text(encoding="utf-8"), end="")
        return 0
    if a.cmd == "seal":
        try:
            summary = seal(out, _path(a.blind), _path(a.seal), force=a.force)
        except (FileExistsError, ValueError) as e:
            print(f"seal: {e}", file=sys.stderr)
            return 1
        print(json.dumps(summary))
        return 0
    rows, manifest = dd.build(
        external_dir=_path(a.external), blind_dir=_path(a.blind),
        agentdojo_dirs=[_path(a.agentdojo_heldout), _path(a.agentdojo_dev)],
        git_sha=_git_sha(), build_date=_dt.date.today().isoformat(),
    )
    dd.write_outputs(out, rows, manifest)
    print(json.dumps({"out": str(out), "totals": manifest["totals"], "blind_present": manifest["blind_present"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
