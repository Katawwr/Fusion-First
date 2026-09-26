"""IFEval — prompts with machine-verifiable instructions ("no commas", "at least 300 words").

Why it is here: it is the external anchor for Fusion's QUALITY dimension (instruction following).
Each instruction is checkable by a deterministic verifier, so it gives ground truth without an LLM
oracle. Only the prompts and instruction specs are imported (there are no reference responses).

Ids reuse the upstream integer ``key`` (``ifeval:1000``) — it is IFEval's own identifier, so it is
stable independent of file order.
"""

from __future__ import annotations

import json
import pathlib

NAME = "ifeval"
URL = "https://huggingface.co/datasets/google/IFEval"
LICENSE = "Apache-2.0"
NOTE = "Prompts + verifiable instruction specs (instruction_id_list aligned with kwargs)."
FILE = "ifeval_input_data.jsonl"


def load_ifeval(raw_dir: pathlib.Path) -> list[dict]:
    """Normalize ``ifeval_input_data.jsonl`` into rows."""
    # Imported lazily: the package __init__ imports this module to build SOURCES.
    from fusion.validate.importers import existing_files

    (path,) = existing_files(raw_dir, [FILE], NAME)
    rows: list[dict] = []
    seen: set[int] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        rec = json.loads(line)
        where = f"{NAME} {path.name}:{lineno}"
        key, prompt = rec.get("key"), rec.get("prompt")
        ids, kwargs = rec.get("instruction_id_list"), rec.get("kwargs")
        if isinstance(key, bool) or not isinstance(key, int):
            raise ValueError(f"{where}: key must be an integer, got {key!r}")
        if key in seen:
            raise ValueError(f"{where}: duplicate key {key}")
        seen.add(key)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{where}: prompt must be a non-empty string")
        if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
            raise ValueError(f"{where}: instruction_id_list must be a list of strings")
        # kwargs[i] parameterizes instruction_id_list[i]; misalignment would verify the wrong thing.
        if not isinstance(kwargs, list) or len(kwargs) != len(ids):
            raise ValueError(f"{where}: kwargs must be a list aligned with instruction_id_list")
        rows.append(
            {
                "id": f"{NAME}:{key}",
                "source": f"external:{NAME}@{path.name}",
                "license": LICENSE,
                "key": key,
                "prompt": prompt,
                "instruction_id_list": ids,
                "kwargs": kwargs,
            }
        )
    return rows
