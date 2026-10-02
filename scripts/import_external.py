"""Import the external benchmarks into normalized, license-checked jsonl + a provenance manifest.

Reads ``datasets/external/raw/<source>/`` (no network) and writes ``datasets/external/<source>.v1.jsonl``
plus ``datasets/external/SOURCES.yaml``.

    python scripts/import_external.py                     # every source; date = newest raw mtime
    python scripts/import_external.py --date 2026-09-26   # pin the import date
    python scripts/import_external.py --only xstest ifeval

Exit codes: 0 ok, 1 missing/malformed raw data, 2 license not allowlisted (nothing written on failure).
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fusion_first._data import data_root  # noqa: E402
from fusion_first.validate.importers import (  # noqa: E402
    SOURCES,
    LicenseNotAllowedError,
    import_all,
    write_manifest,
)


def _iso_date(value: str) -> str:
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc


def main(argv: list[str] | None = None) -> int:
    external = data_root() / "datasets" / "external"
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=pathlib.Path, default=external / "raw",
                    help="root holding one raw/<source>/ directory per source")
    ap.add_argument("--out", type=pathlib.Path, default=external,
                    help="where <source>.v1.jsonl and SOURCES.yaml are written")
    ap.add_argument("--date", type=_iso_date, default=None,
                    help="import date YYYY-MM-DD (default: newest raw file mtime, per source)")
    ap.add_argument("--only", nargs="+", choices=sorted(SOURCES), metavar="SOURCE",
                    help=f"import only these sources (of: {', '.join(sorted(SOURCES))})")
    args = ap.parse_args(argv)

    try:
        entries = import_all(args.raw, args.out, names=args.only, import_date=args.date)
    except LicenseNotAllowedError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1
    manifest = write_manifest(entries, args.out)

    width = max(len(n) for n in entries)
    for name, e in entries.items():
        print(f"{name:<{width}}  {e['rows']:>5} rows  {e['license']:<12}  "
              f"{e['import_date']}  -> {e['processed']}")
    print(f"{sum(e['rows'] for e in entries.values())} rows total; manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
