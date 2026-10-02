"""Error taxonomy: `IsolatableError` (one case is recorded UNSCORED, the run continues) vs
`FatalRunError` (budget, quota, cassette miss, metered auth, allowlist: continuing would spend money,
hide staleness or silently shrink n). `classify()` maps any exception to a countable `ErrorKind`.
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
    """A model provider could not serve one request; `retryable` allows a backed-off retry."""

    retryable: bool = False


class ProviderTimeout(FusionProviderError):
    retryable = True


class ProviderRateLimited(FusionProviderError):
    """Transient throttling (HTTP 429 / 'overloaded')."""

    retryable = True

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderQuotaExhausted(FusionProviderError, FatalRunError):
    """Subscription usage limit reached. Never retried, so a run can't roll into metered overage."""

    def __init__(self, message: str, resets_at: str | None = None):
        super().__init__(message)
        self.resets_at = resets_at


class PromptTooLong(FusionProviderError):
    """Too long to send untruncated; refused up front, since truncation would corrupt the measurement."""


class JudgeUndecided(IsolatableError):
    """A grader could not decide this case: unscored, not guessed."""


class NotGraded(JudgeUndecided):
    """A question its grader never answered. A card with any is never graded: skipping the damning
    questions must not raise a grade."""


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
    if isinstance(exc, FatalRunError):
        return False
    return isinstance(exc, (IsolatableError, TimeoutError))


def classify(exc: BaseException, stage: str = "judge") -> ErrorKind:
    """`stage` is 'target' or 'judge'."""
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
