"""The claims registry: every proof-like number in docs/marketing must resolve to committed evidence.

Shared by `tests/test_claims_backed.py` and (later) `fusion validate claims`. Pure: reads files only.

Fail-closed rules:
  * Evidence must DECLARE `"demonstration": false` (a missing flag counts as a demonstration), unless
    the claim sets `demonstration_ok: true` for deterministic, non-LLM evidence (e.g. the guard bench).
  * Each metric is checked against its OWN denominator (`n_path`/`min_n` per metric), because a rate
    rests on its denominator, not on the total n.
  * The scanner blanks only the exact registered claim spans, then re-scans the rest of the text, in
    single lines AND two-line windows — a registered claim can't shelter a second, unbacked number.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field

import yaml

from fusion._data import data_root

TOLERANCE = 1e-3

# Files whose proof-like numbers must be registered claims.
SCANNED_FILES = (
    "README.md",
    "CLAUDE.md",
    "SCHEMA.md",
    "integrations/README.md",
    "frontend/index.html",
    "fusion/engine/report_html.py",
)
SCANNED_GLOBS = (
    "frontend/src/**/*.jsx",
    "frontend/src/**/*.js",
    "frontend/src/content/*.json",
)

_PCT = r"\d{1,3}(?:\.\d+)?\s*(?:%|percent\b)"
_SEP = r"[\s,:;()\-–—·/]+"
_VOCAB = (
    r"(?:got\s+through|injections?|data[- ]?leaks?|exfil\w*|recall|over[- ]?blocks?|landed|"
    r"attacks?|precision|accuracy|reduction|jailbreaks?|blocked|caught|detect\w*|success\w*|"
    r"fail\w*|landing|leak\w*)"
)
_METRIC = r"(?:F1|kappa|κ|precision|recall|accuracy|landing\s+rate|issue\s+rate|over[- ]?block\s+rate)"

# Patterns that look like a proof claim (a measured rate/accuracy statement).
PROOF_PATTERNS = (
    # "62% injection", "67% of exfiltration attacks landed", "5 percent got through"
    re.compile(rf"\b{_PCT}(?:{_SEP}[\w'-]+){{0,3}}?{_SEP}{_VOCAB}", re.IGNORECASE),
    # "recall 100%", "accuracy of 92%", "issue rate: 40%"
    re.compile(rf"\b{_METRIC}(?:\s+score)?\s*(?:of|=|:|is|was|at|&nbsp;)?\s*{_PCT}", re.IGNORECASE),
    # "F1 1.00", "kappa=0.83", "precision: .9", "F1&nbsp;1.00"
    re.compile(
        rf"\b{_METRIC}(?:\s+score)?\s*(?:of|=|:|is|was|&nbsp;)?\s*(?:[01]?\.\d+|1(?:\.0+)?)(?![\d.%])",
        re.IGNORECASE,
    ),
    # "72% -> 11%", "100% → 8%"
    re.compile(rf"\b{_PCT}\s*(?:->|→|to)\s*{_PCT}", re.IGNORECASE),
    re.compile(r"\bHaiku\s*0\s*%", re.IGNORECASE),
)


@dataclass
class ClaimProblem:
    claim_id: str
    message: str


@dataclass
class Registry:
    claims: list[dict] = field(default_factory=list)
    allowlist: list[dict] = field(default_factory=list)


def repo_root() -> pathlib.Path:
    return data_root()


def load_registry(path: pathlib.Path | None = None) -> Registry:
    p = path or (repo_root() / "evals" / "claims.yaml")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Registry(claims=list(raw.get("claims") or []), allowlist=list(raw.get("allowlist") or []))


def _dig(obj: object, dotted: str) -> object:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur


def _check_n(cid: str, evidence: dict, n_path: str, min_n: int, what: str) -> list[ClaimProblem]:
    try:
        n = _dig(evidence, n_path)
    except KeyError:
        n = None
    if not isinstance(n, int) or isinstance(n, bool) or n < int(min_n):
        return [ClaimProblem(cid, f"{what}: n={n} (at '{n_path}') below min_n={min_n}")]
    return []


def check_claim(claim: dict, root: pathlib.Path) -> list[ClaimProblem]:
    cid = str(claim.get("id", "?"))
    problems: list[ClaimProblem] = []
    ev_path = root / str(claim.get("evidence", ""))
    if not claim.get("evidence") or not ev_path.is_file():
        return [ClaimProblem(cid, f"evidence file missing: {claim.get('evidence')}")]
    try:
        evidence = json.loads(ev_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [ClaimProblem(cid, f"evidence is not JSON: {e}")]
    if not isinstance(evidence, dict):
        return [ClaimProblem(cid, "evidence must be a JSON object")]

    if not claim.get("demonstration_ok", False) and evidence.get("demonstration") is not False:
        problems.append(ClaimProblem(
            cid, "evidence does not declare \"demonstration\": false — stand-in/demo numbers are not claims"
        ))
    for dotted, spec in (claim.get("metrics") or {}).items():
        expected = spec.get("value") if isinstance(spec, dict) else spec
        try:
            actual = _dig(evidence, dotted)
        except KeyError:
            problems.append(ClaimProblem(cid, f"metric '{dotted}' not in evidence"))
            continue
        if (
            not isinstance(actual, (int, float))
            or isinstance(actual, bool)
            or abs(float(actual) - float(expected)) > TOLERANCE
        ):
            problems.append(ClaimProblem(cid, f"metric '{dotted}': claimed {expected}, evidence {actual}"))
        if isinstance(spec, dict) and spec.get("min_n") is not None:
            problems += _check_n(cid, evidence, str(spec.get("n_path", "n")), spec["min_n"], dotted)
    if claim.get("min_n") is not None:
        problems += _check_n(cid, evidence, str(claim.get("n_path", "n")), claim["min_n"], "claim")

    text = str(claim.get("text", ""))
    for rel in claim.get("files") or []:
        f = root / rel
        if not f.is_file() or text not in f.read_text(encoding="utf-8"):
            problems.append(ClaimProblem(cid, f"claim text not found in {rel}"))
    return problems


def scanned_files(root: pathlib.Path) -> list[pathlib.Path]:
    files = [root / rel for rel in SCANNED_FILES if (root / rel).is_file()]
    for pattern in SCANNED_GLOBS:
        files.extend(p for p in sorted(root.glob(pattern)) if "node_modules" not in p.parts)
    seen: set[pathlib.Path] = set()
    return [f for f in files if not (f in seen or seen.add(f))]


def _blank(text: str, spans: list[str]) -> str:
    """Replace every occurrence of each registered span with spaces (same length), so the rest of
    the line is still scanned."""
    for s in sorted({s for s in spans if s}, key=len, reverse=True):
        text = text.replace(s, " " * len(s))
    return text


def _hits(text: str) -> bool:
    return any(p.search(text) for p in PROOF_PATTERNS)


def unregistered_proof_strings(registry: Registry, root: pathlib.Path) -> list[tuple[str, int, str]]:
    """(relative file, line number, line) for every proof-like string not covered by a registered
    claim or allowlist span. Checks single lines and two-line windows (numbers split by a wrap)."""
    out: list[tuple[str, int, str]] = []
    for f in scanned_files(root):
        rel = f.relative_to(root).as_posix()
        spans = [str(c["text"]) for c in registry.claims if rel in (c.get("files") or [])]
        spans += [str(a["text"]) for a in registry.allowlist if a.get("file") == rel]
        raw_lines = f.read_text(encoding="utf-8").splitlines()
        lines = [_blank(ln, spans) for ln in raw_lines]
        flagged: set[int] = set()
        for i, line in enumerate(lines):
            if _hits(line):
                flagged.add(i)
            elif i + 1 < len(lines) and not _hits(lines[i + 1]):
                window = _blank(raw_lines[i].rstrip() + " " + raw_lines[i + 1].lstrip(), spans)
                if _hits(window):
                    flagged.add(i)
        out += [(rel, i + 1, raw_lines[i].strip()) for i in sorted(flagged)]
    return out
