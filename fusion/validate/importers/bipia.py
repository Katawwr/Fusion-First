"""BIPIA — indirect prompt-injection ATTACK PAYLOADS (text and code), nothing else.

Why only payloads: BIPIA's context documents (emails, tables, web pages, code questions) come from
third-party sources with their own terms, so they are never read, let alone redistributed. The attack
instructions themselves are Microsoft's, MIT-licensed, and are what Fusion needs: payloads to splice
into its own tool results.

The loader opens ONLY files named ``{text,code}_attack_{train,test}.json`` (a dict of
category -> list of attack strings). Any other file in the raw dir is ignored by construction.

Ids are ``bipia:<modality>:<split>:<category-slug>:<index>`` — keyed by category name, not file
position, so a reordered upstream dict keeps every id; the raw sha256 in SOURCES.yaml pins the rest.
"""

from __future__ import annotations

import json
import pathlib
import re

NAME = "bipia"
URL = "https://github.com/microsoft/BIPIA"
LICENSE = "MIT"
NOTE = (
    "Attack payloads only. BIPIA context documents carry third-party terms and are deliberately "
    "never imported."
)
MODALITIES = ("text", "code")
SPLITS = ("train", "test")


def slugify(category: str) -> str:
    """``'Scams & Fraud'`` -> ``'scams-fraud'`` (stable, id-safe)."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def load_bipia(raw_dir: pathlib.Path) -> list[dict]:
    """Normalize the attack-payload files into one row per payload."""
    # Imported lazily: the package __init__ imports this module to build SOURCES.
    from fusion.validate.importers import existing_files

    names = [f"{m}_attack_{s}.json" for m in MODALITIES for s in SPLITS]
    rows: list[dict] = []
    for path in existing_files(raw_dir, names, NAME):
        modality, _, split = path.stem.split("_")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{NAME} {path.name}: expected a dict of category -> payloads")
        seen: dict[str, str] = {}
        for category, payloads in data.items():
            slug = slugify(category)
            if not slug or slug in seen:
                raise ValueError(
                    f"{NAME} {path.name}: category {category!r} has an empty or colliding id slug"
                    f" {slug!r} (also {seen.get(slug)!r})"
                )
            seen[slug] = category
            if not isinstance(payloads, list):
                raise ValueError(f"{NAME} {path.name}: {category!r} must map to a list")
            for i, payload in enumerate(payloads):
                if not isinstance(payload, str) or not payload.strip():
                    raise ValueError(
                        f"{NAME} {path.name}: {category!r}[{i}] payload must be a non-empty string"
                    )
                rows.append(
                    {
                        "id": f"{NAME}:{modality}:{split}:{slug}:{i:04d}",
                        "source": f"external:{NAME}@{path.name}",
                        "license": LICENSE,
                        "modality": modality,
                        "split": split,
                        "category": category,
                        "index": i,
                        "payload": payload,
                    }
                )
    return rows
