"""The dataset for the tool-result injection detector (dev-only; nothing here ships in the wheel).

Every row, from every source, has one schema: {id, source, split, technique, request, tool, text, label,
provenance}. `text` is the raw untrusted tool result; `render_frame` is the one frame every system sees. Splits are
fixed by rule, never by hand: InjecAgent ids spent by earlier measured samples are dev, the rest confirmatory;
deepset and BIPIA keep their own train/test; authored carriers and blind negatives split by the parity of
sha256(id); every AgentDojo row is dev (the held-out episodes were spent on the guard). No model calls.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections import Counter

from fusion_first.validate.experiments import SPENT_THROUGH_STEP2, build_items

BUILDER_VERSION = "v1"
SOURCES = ("injecagent", "deepset", "bipia", "agentdojo", "blind")  # also the global dedup order
SPLITS = ("dev", "confirmatory")
PLACEHOLDER = "<Attacker Instruction>"
SLOT = "{PAYLOAD}"
NONE = "(none)"
AUTHORED_LICENSE = "MIT (Fusion First)"
AGENTDOJO_LICENSE = "MIT"
# scripts/step3_guard.py (SALT, N; exclude SPENT_THROUGH_STEP2); a test pins it to the script.
STEP3_SAMPLE = ("fusion-evidence-step3-v1", 150, SPENT_THROUGH_STEP2)
SPENT_SAMPLES = (*SPENT_THROUGH_STEP2, STEP3_SAMPLE)
KIND_TOOLS = {
    "email_body": "read_email",
    "web_article_excerpt": "get_webpage",
    "meeting_notes": "read_file",
    "product_page": "get_product_details",
    "readme_or_code_comment": "read_file",
}
OPEN_TAG, CLOSE_TAG = "<INFORMATION>", "</INFORMATION>"
# AgentDojo attacks whose every injection is wrapped in <INFORMATION>: an untagged result that differs from the
# clean run is the environment's own variation (set order, timestamps, guard blocks), not an injection.
TAGGED_ATTACKS = frozenset({"important_instructions", "tool_knowledge"})
DEFAULT_ATTACK = "important_instructions"  # scripts/agentdojo_guard.py: files without a __<attack> suffix
SOURCE_SPLITS = {"train": "dev", "test": "confirmatory"}  # deepset and BIPIA keep their own split


def render_frame(row: dict) -> str:
    """The single input frame for every row and every system."""
    return f"[REQUEST] {row.get('request') or NONE} [TOOL] {row.get('tool') or NONE} [RESULT] {row['text']}"


def read_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parity_split(key: str) -> str:
    """Even sha256(key) is dev, odd is confirmatory."""
    return SPLITS[int(_sha(key), 16) % 2]


def logical_path(path: pathlib.Path) -> str:
    """A checkout-independent name: from the last datasets/ or evals/ component, else the file name."""
    parts = pathlib.Path(path).parts
    roots = [i for i, p in enumerate(parts) if p in ("datasets", "evals")]
    return "/".join(parts[roots[-1]:]) if roots else parts[-1]


def _row(id_, source, split, technique, request, tool, text, label, provenance) -> dict:
    return {"id": id_, "source": source, "split": split, "technique": technique, "request": request or NONE,
            "tool": tool or NONE, "text": text, "label": label, "provenance": provenance}


def _round_robin(keys: list[str], pool: list[dict]) -> dict[str, dict]:
    """Each key (ranked by sha256) takes the next item of the pool (in id order)."""
    pool = sorted(pool, key=lambda p: p["id"])
    return {k: pool[i % len(pool)] for i, k in enumerate(sorted(keys, key=_sha))}


# ---------------------------------------------------------------- InjecAgent


def spent_injecagent_ids(external_dir: pathlib.Path) -> set[str]:
    """Every InjecAgent id an earlier measured sample used (v1, compact, step 2, step 3)."""
    spent: set[str] = set()
    for salt, n, *exclude in SPENT_SAMPLES:
        items = build_items("injecagent", n, root=external_dir, salt=salt, exclude=exclude[0] if exclude else None)
        spent |= {it.item_id for it in items}
    return spent


def _filler_choice(rows: list[dict], fillers: list[dict]) -> dict[str, dict]:
    """Fillers round-robin over each template's rows, so one template never repeats a filler while any is unused."""
    if not fillers:
        return {}
    groups: dict[str, list[str]] = {}
    for r in rows:
        groups.setdefault(r["tool_response_template"], []).append(r["id"])
    return {k: v for ids in groups.values() for k, v in _round_robin(ids, fillers).items()}


def injecagent_rows(rows: list[dict], *, spent: set[str], fillers: list[dict],
                    source_file: str = "datasets/external/injecagent.v1.jsonl",
                    filler_file: str = "datasets/detector/v1/blind/fillers_c.jsonl") -> list[dict]:
    """A positive per row (the attacker instruction in its slot) and, given fillers, its exact minimal pair."""
    choice = _filler_choice(rows, fillers)
    out = []
    for r in rows:
        tpl, ins = r["tool_response_template"], r["attacker_instruction"]
        if tpl.count(PLACEHOLDER) != 1 or tpl.replace(PLACEHOLDER, ins) != r["tool_response"]:
            raise ValueError(f"{r['id']}: tool_response is not its template filled in")
        split = "dev" if r["id"] in spent else "confirmatory"
        start = tpl.index(PLACEHOLDER)
        prov = {"source_file": source_file, "source_id": r["id"], "license": r.get("license", "MIT")}
        out.append(_row(f"{r['id']}:pos", "injecagent", split, f"injecagent_{r['kind']}", r["user_instruction"],
                        r["user_tool"], r["tool_response"], 1, {**prov, "span": [start, start + len(ins)]}))
        if r["id"] in choice:
            filler = choice[r["id"]]
            out.append(_row(f"{r['id']}:neg", "injecagent", split, "benign_control", r["user_instruction"],
                            r["user_tool"], tpl.replace(PLACEHOLDER, filler["text"]), 0,
                            {**prov, "filler_id": filler["id"], "filler_file": filler_file}))
    return out


# ---------------------------------------------------------------- deepset


def deepset_rows(rows: list[dict], source_file: str = "datasets/external/deepset.v1.jsonl") -> list[dict]:
    """A deepset positive is an injection as a whole: its span is the whole text."""
    out = []
    for r in rows:
        label = int(r["label"])
        prov = {"source_file": source_file, "source_id": r["id"], "license": r.get("license", "Apache-2.0")}
        if label:
            prov["span"] = [0, len(r["text"])]
        out.append(_row(r["id"], "deepset", SOURCE_SPLITS[r["split"]], "deepset", NONE, NONE, r["text"], label, prov))
    return out


# ---------------------------------------------------------------- BIPIA in authored carriers


def _control_text(text: str) -> str:
    """The carrier with its slot emptied; the doubled space the empty slot leaves collapses to one."""
    before, after = text.split(SLOT)
    if before.endswith(" ") and after.startswith(" "):
        after = after[1:]
    return before + after


def bipia_rows(payloads: list[dict], carriers: list[dict],
               source_file: str = "datasets/external/bipia.v1.jsonl") -> list[dict]:
    """Each payload in a carrier of its own split (round-robin by sha256(payload id)); each carrier once empty."""
    for c in carriers:
        if c["text"].count(SLOT) != 1:
            raise ValueError(f"carrier {c['id']}: needs exactly one {SLOT}")
    by_split = {s: [c for c in carriers if parity_split(c["id"]) == s] for s in SPLITS}
    choice: dict[str, dict] = {}
    for split in SPLITS:
        ids = [p["id"] for p in payloads if SOURCE_SPLITS[p["split"]] == split]
        if ids and not by_split[split]:
            raise ValueError(f"no carrier in the {split} split for {len(ids)} BIPIA payloads")
        if ids:
            choice |= _round_robin(ids, by_split[split])
    out = []
    for p in payloads:
        c = choice[p["id"]]
        start = c["text"].index(SLOT)
        out.append(_row(f"{p['id']}@{c['id']}", "bipia", SOURCE_SPLITS[p["split"]], f"bipia:{p['category']}", NONE,
                        KIND_TOOLS[c["kind"]], c["text"].replace(SLOT, p["payload"]), 1,
                        {"source_file": source_file, "source_id": p["id"], "license": p.get("license", "MIT"),
                         "span": [start, start + len(p["payload"])], "carrier_id": c["id"],
                         "carrier_file": c.get("source_file", "carriers")}))
    for c in carriers:
        out.append(_row(f"carrier_control:{c['id']}", "bipia", parity_split(c["id"]), "carrier_control", NONE,
                        KIND_TOOLS[c["kind"]], _control_text(c["text"]), 0,
                        {"source_file": c.get("source_file", "carriers"), "source_id": c["id"],
                         "license": AUTHORED_LICENSE, "carrier_id": c["id"]}))
    return out


# ---------------------------------------------------------------- AgentDojo


def _text(content) -> str:
    return content if isinstance(content, str) else json.dumps(content)


def _tool_results(messages: list[dict]) -> list[tuple[int, str, str, object]]:
    """(message index, tool name, text, the tool_calls of the assistant turn that produced it)."""
    out, call = [], None
    for i, m in enumerate(messages):
        if m.get("role") == "assistant":
            call = m.get("tool_calls")
        elif m.get("role") == "tool":
            out.append((i, m.get("tool_name"), _text(m.get("content")), call))
    return out


def _attack_of(rec: dict, path: pathlib.Path) -> str | None:
    if rec.get("attack"):
        return rec["attack"]
    if rec.get("injection_task") is None:
        return None
    return path.stem.split("__", 1)[1] if "__" in path.stem else DEFAULT_ATTACK


def tag_span(text: str) -> list[int]:
    """From the first <INFORMATION> through the end of the last </INFORMATION> after it (or the end of text)."""
    start = text.index(OPEN_TAG)
    close = text.rfind(CLOSE_TAG)
    return [start, close + len(CLOSE_TAG) if close > start else len(text)]


def diff_span(attacked: str, clean: str) -> list[int]:
    """The middle of `attacked` left after the longest common prefix and suffix with `clean`."""
    p = 0
    while p < min(len(attacked), len(clean)) and attacked[p] == clean[p]:
        p += 1
    s = 0
    while s < min(len(attacked), len(clean)) - p and attacked[-1 - s] == clean[-1 - s]:
        s += 1
    return [p, len(attacked) - s]


def _label(pos: int, name: str, text: str, call, attack, rec: dict, clean: dict | None):
    """(label, span, skip reason) for one tool result of an episode. A tagged result is positive; an attacked
    result is compared with the same model's clean run of the same user task at the same position: equal is
    negative, a differing untagged result of a tagged attack or of a different call is skipped (the difference is
    not the injection), otherwise the differing middle is the injected span."""
    if OPEN_TAG in text:
        return 1, tag_span(text), None
    if rec.get("injection_task") is None:
        return 0, None, None
    if clean is None:
        return None, None, "no_counterpart"
    results = _tool_results(clean["messages"])
    if pos >= len(results) or results[pos][1] != name:
        return None, None, "no_counterpart_result"
    if results[pos][2] == text:
        return 0, None, None
    if attack in TAGGED_ATTACKS:
        return None, None, "untagged_diff_in_tagged_attack"
    if results[pos][3] != call:
        return None, None, "different_call"
    span = diff_span(text, results[pos][2])
    return (1, span, None) if span[1] > span[0] else (None, None, "empty_diff")


def agentdojo_rows(paths: list[pathlib.Path]) -> tuple[list[dict], Counter, int]:
    """Every tool result of every episode, labelled; (rows, skipped by reason, guarded replays dropped)."""
    episodes = [(pathlib.Path(p), n, rec) for p in paths for n, rec in enumerate(read_jsonl(p))]
    clean_runs: dict[tuple, dict] = {}
    for _, _, rec in episodes:
        if rec.get("injection_task") is None and rec.get("arm") == "none":
            clean_runs.setdefault((rec.get("model"), rec["suite"], rec["user_task"]), rec)
    rows, skipped, seen, replays = [], Counter(), set(), 0
    for path, n, rec in episodes:
        attack = _attack_of(rec, path)
        clean = clean_runs.get((rec.get("model"), rec["suite"], rec["user_task"]))
        request = next((_text(m.get("content")) for m in rec["messages"] if m.get("role") == "user"), NONE)
        for pos, (i, name, text, call) in enumerate(_tool_results(rec["messages"])):
            label, span, reason = _label(pos, name, text, call, attack, rec, clean)
            if reason:
                skipped[reason] += 1
                continue
            h = _sha(text)
            if h in seen:
                replays += 1
                continue
            seen.add(h)
            prov = {"source_file": logical_path(path), "source_id": f"{rec['suite']}/{rec['user_task']}/"
                    f"{rec.get('injection_task') or 'none'}/{rec.get('arm')}/{rec.get('model')}#line{n}:msg{i}",
                    "license": AGENTDOJO_LICENSE}
            if span:
                prov["span"] = span
            rows.append(_row(f"agentdojo:{path.parent.name}/{path.stem}:{n}:{i}", "agentdojo", "dev",
                             f"agentdojo:{attack or 'unknown'}" if label else "benign_control", request, name,
                             text, label, prov))
    return rows, skipped, replays


# ---------------------------------------------------------------- blind negatives


def blind_rows(paths: list[pathlib.Path]) -> list[dict]:
    out = []
    for path in paths:
        for r in read_jsonl(path):
            out.append(_row(f"blind:{r['id']}", "blind", parity_split(r["id"]), "blind_negative", r.get("request"),
                            r.get("tool"), r["text"], 0,
                            {"source_file": logical_path(path), "source_id": r["id"], "license": AUTHORED_LICENSE,
                             "kind": r.get("kind"), "trigger_words": r.get("trigger_words"),
                             "length_bucket": r.get("length_bucket"), "style": r.get("style")}))
    return out


# ---------------------------------------------------------------- the build


def dedup(rows: list[dict]) -> tuple[list[dict], Counter]:
    """Drop exact duplicate texts, keeping the first; count drops per source."""
    kept, seen, dropped = [], set(), Counter()
    for r in rows:
        if r["text"] in seen:
            dropped[r["source"]] += 1
        else:
            seen.add(r["text"])
            kept.append(r)
    return kept, dropped


def check(rows: list[dict]) -> None:
    ids = Counter(r["id"] for r in rows)
    dupes = [i for i, n in ids.items() if n > 1]
    if dupes:
        raise ValueError(f"duplicate id(s): {dupes[:5]}")
    texts = {s: {r["text"] for r in rows if r["split"] == s} for s in SPLITS}
    if texts["dev"] & texts["confirmatory"]:
        raise ValueError("a text appears in both splits")
    if any(r["split"] not in SPLITS or r["label"] not in (0, 1) for r in rows):
        raise ValueError("a row has an unknown split or label")
    if any(r["source"] == "agentdojo" and r["split"] != "dev" for r in rows):
        raise ValueError("an AgentDojo row left the dev split")


def _tally(rows: list[dict], distinct: bool) -> dict:
    out: dict = {}
    for source in SOURCES:
        for split in SPLITS:
            sel = [r for r in rows if r["source"] == source and r["split"] == split]
            if sel:
                out.setdefault(source, {})[split] = {
                    str(lab): len({r["text"] for r in sel if r["label"] == lab}) if distinct
                    else sum(r["label"] == lab for r in sel) for lab in (0, 1)}
    return out


def _blind_inputs(blind_dir: pathlib.Path) -> tuple[pathlib.Path | None, list, list]:
    fillers = blind_dir / "fillers_c.jsonl"
    return (fillers if fillers.is_file() else None, sorted(blind_dir.glob("carriers_*.jsonl")),
            sorted(blind_dir.glob("author_*.jsonl")))


def _load_carriers(paths: list[pathlib.Path]) -> list[dict]:
    return [{**c, "source_file": logical_path(p)} for p in paths for c in read_jsonl(p)]


def build(*, external_dir: pathlib.Path, blind_dir: pathlib.Path, agentdojo_dirs: list[pathlib.Path],
          spent: set[str] | None = None, git_sha: str = "", build_date: str = "") -> tuple[list[dict], dict]:
    """Every row (global dedup applied, invariants checked) and the manifest."""
    external_dir, blind_dir = pathlib.Path(external_dir), pathlib.Path(blind_dir)
    fillers_path, carrier_paths, author_paths = _blind_inputs(blind_dir)
    ad_paths = [p for d in agentdojo_dirs if pathlib.Path(d).is_dir() for p in sorted(pathlib.Path(d).glob("*.jsonl"))]
    spent = spent_injecagent_ids(external_dir) if spent is None else spent

    rows = injecagent_rows(read_jsonl(external_dir / "injecagent.v1.jsonl"), spent=spent,
                           fillers=read_jsonl(fillers_path) if fillers_path else [],
                           filler_file=logical_path(fillers_path) if fillers_path else "")
    rows += deepset_rows(read_jsonl(external_dir / "deepset.v1.jsonl"))
    if carrier_paths:
        rows += bipia_rows(read_jsonl(external_dir / "bipia.v1.jsonl"), _load_carriers(carrier_paths))
    ad_rows, skipped, replays = agentdojo_rows(ad_paths)
    rows += ad_rows + blind_rows(author_paths)
    rows, dropped = dedup(rows)
    check(rows)

    inputs = [external_dir / f"{n}.v1.jsonl" for n in ("injecagent", "deepset", "bipia")]
    inputs += ([fillers_path] if fillers_path else []) + carrier_paths + author_paths + ad_paths
    missing = [name for name, ok in (("injecagent negatives", fillers_path), ("bipia rows", carrier_paths),
                                     ("blind negatives", author_paths)) if not ok]
    manifest = {
        "builder_version": BUILDER_VERSION,
        "build_date": build_date,
        "git_sha": git_sha,
        "blind_present": not missing,
        "blind_inputs": {"fillers": bool(fillers_path), "carriers": [p.name for p in carrier_paths],
                         "authors": [p.name for p in author_paths]},
        "skipped_without_blind": missing,
        "agentdojo_files": [logical_path(p) for p in ad_paths],
        "inputs": {logical_path(p): _sha_file(p) for p in inputs},
        "injecagent_spent_ids": len(spent),
        "counts": _tally(rows, distinct=False),
        "distinct_texts": _tally(rows, distinct=True),
        "totals": {s: {str(lab): sum(r["split"] == s and r["label"] == lab for r in rows) for lab in (0, 1)}
                   for s in SPLITS},
        "skipped": {"agentdojo": dict(sorted(skipped.items()))},
        "deduped": {"agentdojo_replay": replays, "global": dict(dropped)},
    }
    return rows, manifest


def _sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def write_outputs(out_dir: pathlib.Path, rows: list[dict], manifest: dict) -> None:
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in rows if r["split"] == split]
        (out_dir / f"{split}.jsonl").write_text("".join(lines), encoding="utf-8", newline="\n")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8", newline="\n")
