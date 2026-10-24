"""Refuse a release whose tag does not name the package version (run by .github/workflows/release.yml).

    python scripts/release_tag_check.py v0.1.1      # exit 1 with the reasons if the tag and the version disagree

The version lives in pyproject.toml and fusion_first/__init__.py, and the bundled plugin pins it; PyPI never accepts
the same version twice, so a mismatch caught here costs nothing and one caught after the upload costs a version.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tomllib


def package_version(root: pathlib.Path) -> str:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def problems(root: pathlib.Path, tag: str) -> list[str]:
    version = package_version(root)
    out = []
    name = tag.removeprefix("refs/tags/")
    if name != f"v{version}":
        out.append(f"tag {name!r} is not v{version} (pyproject.toml)")
    init = (root / "fusion_first" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    if not found or found.group(1) != version:
        out.append(f"fusion_first.__version__ is not {version}")
    mcp = json.loads((root / "plugins" / "fusion" / ".mcp.json").read_text(encoding="utf-8"))
    if f"fusion-safety=={version}" not in json.dumps(mcp):
        out.append(f"plugins/fusion/.mcp.json does not pin fusion-safety=={version}")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    found = problems(pathlib.Path(__file__).resolve().parents[1], sys.argv[1])
    for p in found:
        print(f"release refused: {p}")
    if not found:
        print(f"tag {sys.argv[1]} matches version {package_version(pathlib.Path(__file__).resolve().parents[1])}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
