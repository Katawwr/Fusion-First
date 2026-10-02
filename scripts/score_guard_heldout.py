"""Score a blind fusion-guard held-out corpus ONCE and write its evidence file.

    python scripts/score_guard_heldout.py --version v3 --rules-sha f7d3809 \
        --corpus datasets/guard_bench/claude_code_heldout_v3.jsonl \
        --out evals/guard_bench/claude_code_heldout_v3.json

Refuses to overwrite existing evidence or to score if the hook's rules differ from the registered commit.
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

from fusion_first.validate.guard_heldout import score_heldout  # noqa: E402

RULES = "fusion_first/integrations/claude_hooks.py"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="score_guard_heldout")
    p.add_argument("--corpus", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--rules-sha", required=True, help="the commit the corpus was registered against")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    out = ROOT / a.out
    if out.exists():
        print(f"refusing: {a.out} exists: a held-out set is scored once")
        return 2
    if _git("diff", "--quiet", a.rules_sha, "--", RULES).returncode != 0:
        print(f"refusing: {RULES} differs from the registered rules at {a.rules_sha}")
        return 2
    sha = _git("rev-parse", a.rules_sha).stdout.strip()
    rows = [json.loads(line) for line in (ROOT / a.corpus).read_text(encoding="utf-8").splitlines() if line.strip()]
    evidence = {
        "demonstration": False,
        "kind": f"fusion-guard Claude Code hook - held-out benchmark {a.version} (written blind to the rules "
                "by independent agents; scored once, never tuned on)",
        "corpus": a.corpus,
        "rules_git_sha": sha,
        "measured": _dt.date.today().isoformat(),
        **score_heldout(rows),
        "status": f"HELD OUT at rules_git_sha. Any rule change after this measurement makes {a.version} a dev "
                  "set; the next honest number needs a fresh blind corpus.",
    }
    out.write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8", newline="\n")
    b, m = evidence["benign"], evidence["malicious"]
    print(f"{a.version}: benign prompted {b['prompted']}/{b['n']} ({b['over_block']['point']:.0%}), "
          f"attacks caught {m['caught']}/{m['n']} ({m['recall']['point']:.0%}) -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
