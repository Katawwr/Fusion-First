"""One error taxonomy for the whole engine: what failed, and whether the run may continue.

Two families decide control flow:

* `IsolatableError` — ONE case failed (a target timed out, a judge answer was unparseable). The
  case is recorded as UNSCORED (never as clean, never as a violation) and the run continues.
* `FatalRunError` — the RUN must stop (budget exhausted, subscription quota hit, a strict-replay
  cassette miss, metered auth refused, a model off the allowlist). Continuing would either spend
  money, hide staleness, or silently shrink n — so these always propagate.

`ErrorKind` + `classify()` turn any exception into a stable, countable category for the reliability
block on every report card ("scored 23/24 — 1 unscored: judge timeout").
"""

from __future__ import annotations

from enum import Enum


class FusionError(Exception):
    """Base for Fusion-raised errors."""


class IsolatableError(FusionError):
    """A single case failed; record it as unscored and continue the run."""


class FatalRunError(FusionError):
    """The whole run must stop; never swallowed per case."""


class FusionProviderError(RuntimeError, IsolatableError):
    """A model provider could not serve one request. `retryable` says whether an immediate
    (backed-off) retry is sensible."""

    retryable: bool = False


class ProviderTimeout(FusionProviderError):
    retryable = True


class ProviderRateLimited(FusionProviderError):
    """Transient throttling (HTTP 429 / 'overloaded'). Retried with jittered backoff."""

    retryable = True

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderQuotaExhausted(FusionProviderError, FatalRunError):
    """The subscription's usage limit was reached. NEVER retried: stopping here is what guarantees a
    run can't roll into metered overage. Resume after the reset."""

    def __init__(self, message: str, resets_at: str | None = None):
        super().__init__(message)
        self.resets_at = resets_at


class PromptTooLong(FusionProviderError):
    """The request cannot be sent without truncation (OS argv limit or model context window).
    Refused up front — a silently truncated system prompt would corrupt the measurement."""


class JudgeUndecided(IsolatableError):
    """A grader (e.g. a deterministic verifier) could not decide this case — unscored, not guessed."""


class NotGraded(JudgeUndecided):
    """A run's question was never answered by its grader (partial finalize). Unscored, and a card
    with any such question is never graded: skipping the damning questions must not raise a grade."""


class ErrorKind(str, Enum):
    TARGET_ERROR = "target_error"
    TARGET_TIMEOUT = "target_timeout"
    JUDGE_ERROR = "judge_error"
    JUDGE_TIMEOUT = "judge_timeout"
    JUDGE_PARSE = "judge_parse"
    UNDECIDABLE = "undecidable"
    NOT_GRADED = "not_graded"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    PROMPT_TOO_LONG = "prompt_too_long"
    BUDGET_EXCEEDED = "budget_exceeded"
    CASSETTE_MISS = "cassette_miss"
    MODEL_NOT_ALLOWED = "model_not_allowed"
    AUTH_REFUSED = "auth_refused"
    INTERNAL = "internal"


def isolatable(exc: BaseException) -> bool:
    """True if this failure affects one case only (record as unscored, keep going)."""
    if isinstance(exc, FatalRunError):
        return False
    return isinstance(exc, (IsolatableError, TimeoutError))


def classify(exc: BaseException, stage: str = "judge") -> ErrorKind:
    """Map an exception to a countable ErrorKind. `stage` is 'target' or 'judge'."""
    name = type(exc).__name__
    if isinstance(exc, ProviderQuotaExhausted):
        return ErrorKind.QUOTA_EXHAUSTED
    if isinstance(exc, ProviderRateLimited):
        return ErrorKind.RATE_LIMITED
    if isinstance(exc, PromptTooLong):
        return ErrorKind.PROMPT_TOO_LONG
    # Classes defined elsewhere are matched by name to keep this module import-cycle free.
    if name == "PaidAuthRefused":
        return ErrorKind.AUTH_REFUSED
    if name == "BudgetExceeded":
        return ErrorKind.BUDGET_EXCEEDED
    if name == "CassetteMiss":
        return ErrorKind.CASSETTE_MISS
    if name == "ModelNotAllowed":
        return ErrorKind.MODEL_NOT_ALLOWED
    if name == "JudgeParseError":
        return ErrorKind.JUDGE_PARSE
    if isinstance(exc, NotGraded):
        return ErrorKind.NOT_GRADED
    if isinstance(exc, JudgeUndecided):
        return ErrorKind.UNDECIDABLE
    timeout = isinstance(exc, (TimeoutError, ProviderTimeout))
    if stage == "target":
        return ErrorKind.TARGET_TIMEOUT if timeout else ErrorKind.TARGET_ERROR
    if timeout:
        return ErrorKind.JUDGE_TIMEOUT
    if isinstance(exc, FusionProviderError):
        return ErrorKind.JUDGE_ERROR
    return ErrorKind.INTERNAL
