"""Build the tool-result injection detector's dataset (dev-only; offline; no model calls).

    python scripts/detector_data.py build [--out datasets/detector/v1] [--blind datasets/detector/v1/blind]
        [--agentdojo-heldout evals/validation/v1/agentdojo/heldout] [--agentdojo-dev evals/validation/v1/agentdojo/dev]
    python scripts/detector_data.py stats [--out datasets/detector/v1]

Writes dev.jsonl, confirmatory.jsonl and manifest.json. Missing blind inputs are skipped and recorded in the manifest.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate import detector_data as dd  # noqa: E402

OUT = ROOT / "datasets/detector/v1"


def _git_sha() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return r.stdout.strip()


def _path(p: str) -> pathlib.Path:
    path = pathlib.Path(p)
    return path if path.is_absolute() else ROOT / path


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
    a = ap.parse_args(argv)

    out = _path(a.out)
    if a.cmd == "stats":
        print((out / "manifest.json").read_text(encoding="utf-8"), end="")
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
