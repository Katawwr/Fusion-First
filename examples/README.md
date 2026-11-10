# Verified example runs

Real runs, committed with their recordings (target replies, judge requests and answers). `fusion run verify`
re-derives each result offline from those recordings and exits non-zero on any drift; CI runs it on every push.
Card numbers live in each run's `result.json` and `report.html`, not here.

| Workspace | Run | Target | Tier | Judge prompt | Shows |
|---|---|---|---|---|---|
| `verified-run` | `f9388f6e9b11` | llama3.2:1b | Quick | version 2 | The four checks on the text corpus. |
| `verified-run-toolloop` | `45eb15bc9e0e` | qwen2.5:7b | Full | version 2 | The tool loop (`--corpus v2`). One grade is withheld: the grader called a send the oracle confirmed clean, and the in-run gate withholds on any such miss. |
| `verified-run-toolloop` | `0fbaa0f1985e` | qwen2.5:7b | Full | version 3 | The same scan re-graded with claimed actions and pasted secrets counting. No grade is withheld. |

The two tool-loop runs share their target replies (the target is deterministic); only the grading differs.
`latest` resolves to the run started last, so it is the version 3 run there.

```bash
pip install -e .
fusion run verify --workspace examples/verified-run f9388f6e9b11
fusion run verify --workspace examples/verified-run-toolloop 45eb15bc9e0e
fusion run verify --workspace examples/verified-run-toolloop 0fbaa0f1985e
```

Each run was graded by Claude Code host subagents under a blindness instruction. Why a grade can be withheld:
[architecture](../docs/ARCHITECTURE.md). Why version 3 exists: [design note](../docs/design/rubric-claims-wording.md).
