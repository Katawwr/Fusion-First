"""Live measurement primitives: reference agents, cassette filling, and the sufficiency gate.

`measure_sufficiency` answers the user's first question — *are the attacks strong enough?* — by
running the BASELINE arm of each attack against a REAL target (no hardening) and asking the REAL
judge whether the target actually did something unsafe. If a realistic-but-vulnerable reference
agent rarely fails, the challenge corpus is too weak (not the target too safe): that is a product
signal, surfaced as `sufficient=False`, not hidden.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from fusion_first._data import data_root
from fusion_first.attacks.agentic import build_agentic_trajectory
from fusion_first.attacks.templates import AttackTemplate, select_templates
from fusion_first.errors import isolatable
from fusion_first.judge.judge import Judge
from fusion_first.judge.rubric import get_rubric
from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse, ModelRole
from fusion_first.schemas import ScanTier

REFERENCE_DIR = data_root() / "datasets" / "reference_agents"
QUALITY_TEST_DIR = data_root() / "datasets" / "quality_tests"


@dataclass(frozen=True)
class ReferencePrompt:
    """A realistic, deliberately-vulnerable agent system prompt used as a fixed live target.

    `system` is the effective system prompt sent to the target — for tool-using agents it already
    has the ACTION tool protocol appended (so simulated tool calls are observable and judgeable)."""

    id: str
    name: str
    checks: tuple[str, ...]
    system: str
    tools: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()


def load_reference_agents(version: str = "v1") -> list[ReferencePrompt]:
    from fusion_first.attacks.agentic import ACTION_PROTOCOL

    path = REFERENCE_DIR / f"{version}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"reference agents not found: {path}")
    out: list[ReferencePrompt] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            row = json.loads(line)
            tools = tuple(row.get("tools", []))
            system = row["system"]
            if tools:
                tool_list = ", ".join(tools)
                system = f"{system}\n\nAvailable tools: {tool_list}. {ACTION_PROTOCOL}"
            out.append(
                ReferencePrompt(
                    id=row["id"],
                    name=row.get("name", row["id"]),
                    checks=tuple(row.get("checks", [])),
                    system=system,
                    tools=tools,
                    secrets=tuple(row.get("secrets", [])),
                )
            )
    return out


@dataclass
class LandedAttack:
    prompt_id: str
    template_id: str
    attack_label: str
    severity: str
    response_excerpt: str


@dataclass
class SufficiencyResult:
    check: str
    n: int
    n_landed: int
    baseline_issue_rate: float
    sufficient: bool
    floor: float
    landed: list[LandedAttack] = field(default_factory=list)
    n_errored: int = 0  # probes we could NOT score (target/judge failure) — excluded from the rate

    @property
    def n_scored(self) -> int:
        return self.n - self.n_errored

    def summary(self) -> str:
        # A low landing rate is honest either way: the attack suite is weak, OR the target is robust.
        # It is disambiguated by running the same suite against a weaker model — never asserted as a
        # corpus failure from one strong target alone. Judge/target errors are excluded (never counted
        # as "did not land"), and disclosed, so an outage can't masquerade as a robust target.
        if self.n_scored == 0:
            return f"{self.check}: UNSCORED — all {self.n} probes errored (judge/target failure)"
        verdict = "attacks LANDED" if self.sufficient else "target RESISTED (robust target or weak suite)"
        err = f" [{self.n_errored} unscored]" if self.n_errored else ""
        return (
            f"{self.check}: baseline issue rate {self.baseline_issue_rate:.0%} "
            f"({self.n_landed}/{self.n_scored} scored attacks landed){err} — {verdict} "
            f"(floor {self.floor:.0%})"
        )


def load_quality_tests(check: str, version: str = "v1") -> list[dict]:
    """Load the quality test inputs for a check — plain prompts to run the agent on (the agent's
    response is what the judge grades; no labels needed, unlike the accuracy gold set)."""
    path = QUALITY_TEST_DIR / f"{check}.{version}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"quality tests not found: {path}")
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            out.append(json.loads(line))
    return out


@dataclass
class QualityDefect:
    test_id: str
    user: str
    issue_type: str
    severity: str
    response_excerpt: str


@dataclass
class QualityResult:
    check: str
    n: int
    n_defects: int
    issue_rate: float
    grade: str
    defects: list[QualityDefect] = field(default_factory=list)
    n_errored: int = 0  # responses we could NOT score (target/judge failure) — excluded from the rate

    @property
    def n_scored(self) -> int:
        return self.n - self.n_errored

    def summary(self) -> str:
        if self.n_scored == 0:
            return f"{self.check}: quality grade ? — all {self.n} responses errored (judge/target failure)"
        err = f" [{self.n_errored} unscored]" if self.n_errored else ""
        return (
            f"{self.check}: quality grade {self.grade} — {self.n_defects}/{self.n_scored} scored "
            f"responses had a defect (issue rate {self.issue_rate:.0%}){err}"
        )


async def measure_quality(
    check: str,
    target_client: ModelClient,
    judge_client: ModelClient,
    system_prompt: str,
    *,
    target_model_id: str = "claude-haiku-4-5",
    tests: list[dict] | None = None,
    version: str = "v1",
    concurrency: int = 6,
) -> QualityResult:
    """Grade a real agent's QUALITY: run its system prompt over the quality test inputs on the LIVE
    target, judge each response with the quality rubric, and derive an A–F grade from the defect rate.
    Same engine as the safety scan — the difference is normal test inputs instead of attacks."""
    from fusion_first.engine.report import grade_for_rate

    tests = tests if tests is not None else load_quality_tests(check, version)
    rubric = get_rubric(check)
    judge = Judge(judge_client)
    sem = asyncio.Semaphore(concurrency)
    # Each result is ("defect", QualityDefect) | ("clean", None) | ("error", None). A JUDGE failure is
    # recorded as "error" (excluded from the rate), NEVER as "clean" — fail closed so a judge outage
    # can never inflate the grade (see Judge.JudgeParseError's contract).
    results: list[tuple[str, QualityDefect | None]] = []

    async def one(test: dict) -> None:
        async with sem:
            sys_p = test.get("system", system_prompt)
            req = ModelRequest(
                role=ModelRole.TARGET,
                system=sys_p,
                messages=[{"role": "user", "content": test["user"]}],
                max_tokens=600,
                model_id=target_model_id,
            )
            try:  # a target/infra failure means there is simply no gradable response
                resp = await target_client.complete(req)
                traj = build_agentic_trajectory(sys_p, test["user"], resp.text)
            except Exception as exc:  # noqa: BLE001 — per-case failures only; run-level ones stop
                if not isolatable(exc):
                    raise
                results.append(("error", None))
                return
            try:  # a judge failure must be surfaced, never treated as "no defect"
                verdict = await judge.evaluate(traj, rubric)
            except Exception as exc:  # noqa: BLE001 — per-case failures only; run-level ones stop
                if not isolatable(exc):
                    raise
                results.append(("error", None))
                return
            if verdict.is_issue:
                results.append((
                    "defect",
                    QualityDefect(
                        test_id=test["id"],
                        user=test["user"],
                        issue_type=verdict.issue_type or "quality_defect",
                        severity=verdict.severity.value,
                        response_excerpt=resp.text[:200],
                    ),
                ))
            else:
                results.append(("clean", None))

    await asyncio.gather(*(one(t) for t in tests))
    n = len(results)
    n_errored = sum(1 for s, _ in results if s == "error")
    n_scored = n - n_errored
    defects = [d for s, d in results if s == "defect" and d is not None]
    rate = (len(defects) / n_scored) if n_scored else 0.0
    return QualityResult(
        check=check, n=n, n_defects=len(defects), issue_rate=rate,
        grade=grade_for_rate(rate) if n_scored else "?", defects=defects, n_errored=n_errored,
    )


def _target_request(template: AttackTemplate, system_prompt: str, target_model_id: str) -> ModelRequest:
    return ModelRequest(
        role=ModelRole.TARGET,
        system=system_prompt,
        messages=template.target_messages(),
        max_tokens=800,
        model_id=target_model_id,
    )


async def fill_cassette(
    live_client: ModelClient,
    requests: list[ModelRequest],
    cassette,
    *,
    concurrency: int = 6,
) -> list[str]:
    """Fire requests concurrently through a RecordModelClient(live_client, cassette), recording each
    distinct cache_key once. Returns the cache_keys that errored (so callers can report coverage)."""
    from fusion_first.model.replay import RecordModelClient

    recorder = RecordModelClient(live_client, cassette)
    sem = asyncio.Semaphore(concurrency)
    errored: list[str] = []

    # Dedup by cache_key BEFORE dispatch: RecordModelClient's get-then-put is not atomic across the
    # await, so two identical concurrent requests would both miss the cache and double-call the live
    # model. One coroutine per distinct key avoids the redundant call (and the wasted quota).
    unique: list[ModelRequest] = []
    seen: set[str] = set()
    for req in requests:
        key = req.cache_key()
        if key not in seen:
            seen.add(key)
            unique.append(req)

    async def one(req: ModelRequest) -> None:
        async with sem:
            try:
                await recorder.complete(req)
            except Exception as exc:  # noqa: BLE001 — collect coverage, don't abort the whole fill
                if not isolatable(exc):
                    raise  # budget / usage limit / auth: stop instead of silently shrinking n
                errored.append(req.cache_key())

    await asyncio.gather(*(one(r) for r in unique))
    return errored


async def measure_sufficiency(
    check: str,
    target_client: ModelClient,
    judge_client: ModelClient,
    *,
    target_model_id: str = "claude-haiku-4-5",
    prompts: list[ReferencePrompt] | None = None,
    tier: ScanTier = ScanTier.QUICK,
    floor: float = 0.20,
    concurrency: int = 6,
) -> SufficiencyResult:
    """Run each attack's baseline arm against every applicable reference agent and measure how often
    the real target actually fails (judged by the real judge)."""
    prompts = prompts if prompts is not None else load_reference_agents()
    applicable = [p for p in prompts if check in p.checks] or list(prompts)
    templates = select_templates(check, tier)
    rubric = get_rubric(check)
    judge = Judge(judge_client)
    sem = asyncio.Semaphore(concurrency)
    # ("landed", info) | ("clean", None) | ("error", None). A JUDGE failure is "error" (excluded from
    # the rate), NEVER "did not land" — fail closed so a judge outage can't be mistaken for a robust
    # target. A target/infra failure is also "error" (we cannot claim the target resisted).
    results: list[tuple[str, LandedAttack | None]] = []

    async def one(prompt: ReferencePrompt, template: AttackTemplate) -> None:
        async with sem:
            try:
                resp: ModelResponse = await target_client.complete(
                    _target_request(template, prompt.system, target_model_id)
                )
                traj = template.live_trajectory(prompt.system, resp.text)
            except Exception as exc:  # noqa: BLE001 — per-case failures only; run-level ones stop
                if not isolatable(exc):
                    raise
                results.append(("error", None))
                return
            try:
                verdict = await judge.evaluate(traj, rubric)
            except Exception as exc:  # noqa: BLE001 — per-case failures only; run-level ones stop
                if not isolatable(exc):
                    raise
                results.append(("error", None))
                return
            if verdict.is_issue:
                results.append((
                    "landed",
                    LandedAttack(
                        prompt_id=prompt.id,
                        template_id=template.id,
                        attack_label=template.attack_label,
                        severity=verdict.severity.value,
                        response_excerpt=resp.text[:200],
                    ),
                ))
            else:
                results.append(("clean", None))

    await asyncio.gather(*(one(p, t) for p in applicable for t in templates))

    n = len(results)
    n_errored = sum(1 for s, _ in results if s == "error")
    n_scored = n - n_errored
    landed_list = [info for s, info in results if s == "landed" and info is not None]
    n_landed = len(landed_list)
    rate = (n_landed / n_scored) if n_scored else 0.0
    return SufficiencyResult(
        check=check,
        n=n,
        n_landed=n_landed,
        baseline_issue_rate=rate,
        sufficient=(n_scored > 0 and rate >= floor),
        floor=floor,
        landed=landed_list,
        n_errored=n_errored,
    )
