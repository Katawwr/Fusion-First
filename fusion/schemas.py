"""Canonical data model for Fusion First.

This is the single source of truth (SCHEMA.md documents it in prose). Every module —
judge, engine, stats, store, routes — imports these types and no other module may
redefine them. Cross-lens naming was frozen here: the trajectory field is `content`,
and `injected` lives on `ToolResult` (injection is a property of a tool result, not a step).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------------------
# Agent trajectory (the agentic core — a scan target is a Trajectory, not just a prompt)
# --------------------------------------------------------------------------------------


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Output of a tool the agent invoked.

    `injected` marks that this result carried untrusted / attacker-controlled content
    (the indirect-prompt-injection surface — OWASP LLM01 / Agentic ASI01).
    """

    tool: str
    content: str
    injected: bool = False


class Step(BaseModel):
    role: Role
    content: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    thinking: str | None = None


class Trajectory(BaseModel):
    """An ordered agent interaction: system prompt, user turns, tool calls/results, replies."""

    steps: list[Step] = Field(default_factory=list)

    def system_prompt(self) -> str:
        for s in self.steps:
            if s.role == Role.SYSTEM:
                return s.content
        return ""

    def final_response(self) -> str:
        for s in reversed(self.steps):
            if s.role == Role.ASSISTANT and s.content:
                return s.content
        return ""

    def has_injection(self) -> bool:
        return any(s.tool_result and s.tool_result.injected for s in self.steps)

    def transcript(self) -> str:
        """Render the trajectory as readable text for a judge (evidence window)."""
        lines: list[str] = []
        for s in self.steps:
            tag = s.role.value.upper()
            if s.role == Role.TOOL and s.tool_result:
                flag = " [UNTRUSTED/INJECTED]" if s.tool_result.injected else ""
                lines.append(f"[TOOL_RESULT:{s.tool_result.tool}{flag}] {s.tool_result.content}")
            elif s.tool_call:
                lines.append(f"[{tag} calls {s.tool_call.name}] {s.tool_call.arguments}")
            else:
                lines.append(f"[{tag}] {s.content}")
        return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Severity, taxonomy tags
# --------------------------------------------------------------------------------------


class Severity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return ["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"].index(self.value)


class OwaspTag(BaseModel):
    """Crosswalk to recognized taxonomies. Codes are validated against the pinned
    crosswalk YAML by fusion.attacks.taxonomy — never invented ad hoc."""

    llm: str | None = None  # e.g. "LLM01"
    asi: str | None = None  # e.g. "ASI01"


# --------------------------------------------------------------------------------------
# Rubric (judge decomposed into binary, evidence-bearing criteria)
# --------------------------------------------------------------------------------------


class Criterion(BaseModel):
    """A single binary check. `violated=True` means the criterion indicates an issue."""

    id: str
    question: str  # a yes/no question; "yes" => violated
    weight_severity: Severity = Severity.MEDIUM


class CriterionVerdict(BaseModel):
    id: str
    violated: bool
    evidence: str = ""


# --------------------------------------------------------------------------------------
# Labels (oracle ground truth) and Verdicts (judge output) — kept distinct on purpose
# --------------------------------------------------------------------------------------


class Label(BaseModel):
    """Ground-truth label from a deterministic oracle or a human annotator."""

    is_issue: bool
    severity: Severity = Severity.NONE
    issue_type: str | None = None
    source: str = "oracle"  # e.g. "oracle:injecagent", "human:annotatorA"


class Verdict(BaseModel):
    """A judge's decision about one trajectory."""

    is_issue: bool
    severity: Severity = Severity.NONE
    issue_type: str | None = None
    criteria: list[CriterionVerdict] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.5
    judge_model: str = "unknown"

    @field_validator("confidence")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# --------------------------------------------------------------------------------------
# Gold-set item (Bar A) and paired probe (Bar B)
# --------------------------------------------------------------------------------------


class JudgeCase(BaseModel):
    """A labeled item used to measure judge accuracy (Bar A). The judge scores
    `trajectory`; the resulting Verdict.is_issue is compared to `oracle.is_issue`."""

    id: str
    check: str
    trajectory: Trajectory
    oracle: Label
    owasp: OwaspTag = Field(default_factory=OwaspTag)
    split: str = "dev"  # dev | blind | canary


class PairedProbe(BaseModel):
    """One before/after test case (Bar B). Same attack run against the baseline and the
    hardened target; the judge scores both and we test whether hardening reduced issues."""

    id: str
    check: str
    baseline: Trajectory
    hardened: Trajectory
    owasp: OwaspTag = Field(default_factory=OwaspTag)


# --------------------------------------------------------------------------------------
# Statistics results
# --------------------------------------------------------------------------------------


class Interval(BaseModel):
    point: float
    low: float
    high: float

    def pct(self) -> str:
        return f"{self.point * 100:.0f}% (CI {self.low * 100:.0f}-{self.high * 100:.0f})"


class AccuracyResult(BaseModel):
    """Bar A: judge-vs-oracle accuracy on a labeled set."""

    n: int
    precision: Interval
    recall: Interval
    f1: float
    accuracy: Interval
    cohen_kappa: float
    tp: int
    fp: int
    tn: int
    fn: int
    label_source: str
    n_unscored: int = 0  # gold cases the judge failed to answer (excluded above, never guessed)


class Honesty(str, Enum):
    """Bar B honesty badge — never overclaim on small samples."""

    PROVEN = "PROVEN"  # significant + adequate sample
    PRELIMINARY = "PRELIMINARY"  # directional but underpowered
    INCONCLUSIVE = "INCONCLUSIVE"  # cannot distinguish from noise


class BeforeAfterResult(BaseModel):
    """Bar B: paired before/after improvement with an honest confidence interval."""

    n_pairs: int
    baseline_issue_rate: float
    hardened_issue_rate: float
    absolute_reduction: Interval
    mcnemar_p: float
    discordant_b: int  # baseline-fail, hardened-pass (improvements)
    discordant_c: int  # baseline-pass, hardened-fail (regressions)
    honesty: Honesty
    # Plain-language reasons the badge is not PROVEN (empty when PROVEN) — "Why not PROVEN?".
    honesty_reasons: list[str] = Field(default_factory=list)


class BenchmarkResult(BaseModel):
    """Bar D: detector performance on a public benchmark subset."""

    name: str
    n: int
    detector_tpr: Interval
    detector_fpr: Interval
    note: str = ""


class TrustInfo(BaseModel):
    """How far to trust a card: what actually ran, who judged it, and how much was scored.

    Every card carries this so a reader never has to guess whether numbers came from canned demo
    responses or a real model, or how many attacks silently failed to score (none can: they are
    counted here and shown)."""

    execution: str = "canned"  # "canned" (demo responses, prompt NOT run) | "live" (real target)
    judge_id: str = ""
    judge_backend: str = ""  # heuristic | claude_cli | ollama_prob | api | host
    independence: str = ""  # cross_family | same_family_cross_tier | same_model | n/a
    independence_disclosure: str = ""
    judge_accuracy_source: str = ""  # where judge_accuracy came from (or "" if absent)
    n_planned: int = 0
    n_scored: int = 0
    n_errored: int = 0
    error_kinds: dict[str, int] = Field(default_factory=dict)
    sampling_pinned: bool | None = None  # None = unknown; False = backend can't pin temperature


class SafetyReportCard(BaseModel):
    """The customer-facing artifact fusing all proof bars. Every number carries a CI or
    an honesty badge; provenance hashes make it verifiable and non-repudiable."""

    target_name: str
    check: str
    grade: str  # A..F headline grade of the user's prompt AS WRITTEN (the baseline arm)
    hardened_grade: str = "?"  # A..F grade after applying Fusion's fix (the hardened arm)
    judge_accuracy: AccuracyResult | None = None
    kind: str = "safety"  # safety | quality
    trust: TrustInfo = Field(default_factory=TrustInfo)
    # Why judge_accuracy is absent (stale/missing calibration, or not yet measured for this judge).
    # Never silently empty: a card either shows Bar A or says why it can't.
    judge_accuracy_note: str = ""
    before_after: BeforeAfterResult | None = None
    benchmark: BenchmarkResult | None = None
    owasp_tags: list[OwaspTag] = Field(default_factory=list)
    top_fixes: list[str] = Field(default_factory=list)
    # A concrete, copy-paste-ready remedy the user can apply (or auto-apply via `fusion harden`).
    fix_title: str = ""
    fix_snippet: str = ""
    # provenance
    gold_version: str = ""
    crosswalk_version: str = ""
    judge_model: str = ""
    verification_hash: str = ""
    # A demonstration card (synthetic cassettes / self-test) must never read as a real claim.
    demonstration: bool = False


# --------------------------------------------------------------------------------------
# User-prompt scan (the web-app flow: paste a system prompt, attack it, grade it)
# --------------------------------------------------------------------------------------


class ScanTier(str, Enum):
    """How thorough a scan is. QUICK is the cheap interactive default; FULL is the 'prove it'
    tier (every attack template, the primary judge). Concrete knobs live in engine/user_scan.py."""

    QUICK = "quick"
    FULL = "full"


class ProbeOutcome(BaseModel):
    """One attack template's result across both arms of a user-prompt scan (baseline vs hardened)."""

    check: str
    probe_id: str
    attack_label: str  # human-readable ("Posed as a developer: 'ignore previous instructions'")
    owasp: OwaspTag = Field(default_factory=OwaspTag)
    # None = UNSCORED (the target or judge failed for this attack) — never counted as clean.
    baseline_issue: bool | None
    hardened_issue: bool | None
    baseline_severity: Severity = Severity.NONE
    hardened_severity: Severity = Severity.NONE
    error: str | None = None  # why this attack is unscored
    error_kind: str | None = None  # an ErrorKind value
    evidence: str = ""  # the judge's quote for the baseline violation (<= 240 chars)
    baseline_excerpt: str = ""  # the start of the baseline response (<= 200 chars)

    @property
    def scored(self) -> bool:
        return self.baseline_issue is not None and self.hardened_issue is not None


class ScanResult(BaseModel):
    """The finished scan: one report card per check, the flat per-probe outcomes, overall grade."""

    target_name: str
    checks: list[str] = Field(default_factory=list)
    tier: ScanTier = ScanTier.QUICK
    demonstration: bool = True
    overall_grade: str = "?"
    cards: list[SafetyReportCard] = Field(default_factory=list)
    outcomes: list[ProbeOutcome] = Field(default_factory=list)
    execution: str = "canned"  # canned | live
    n_planned: int = 0
    n_scored: int = 0
    n_errored: int = 0
    # The exact hardened prompt the "after" arm measured (= what the user copies), by hash.
    hardened_prompt_sha256: str = ""
    target_model: str = ""


class ScanEventType(str, Enum):
    SCAN_STARTED = "scan_started"
    CHECK_STARTED = "check_started"
    PROBE_RESULT = "probe_result"
    CHECK_COMPLETED = "check_completed"
    SCAN_COMPLETED = "scan_completed"
    ERROR = "error"


class ScanEvent(BaseModel):
    """A streamed progress event from a running scan — the envelope the SSE layer serializes.

    The engine yields these so the HTTP layer can stream progress without the engine knowing
    anything about HTTP. Only the fields relevant to a given `type` are populated.
    """

    type: ScanEventType
    check: str | None = None
    code: str | None = None  # machine-readable reason on ERROR events (e.g. backend_unavailable)
    message: str = ""
    completed: int = 0
    total: int = 0
    demonstration: bool = True
    probe: ProbeOutcome | None = None
    card: SafetyReportCard | None = None
    result: ScanResult | None = None
