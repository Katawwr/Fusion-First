"""The error taxonomy decides whether a failure costs one case or stops the whole run."""

from __future__ import annotations

import pytest

from fusion_first.errors import (
    ErrorKind,
    FatalRunError,
    PromptTooLong,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderTimeout,
    classify,
    isolatable,
)
from fusion_first.judge.judge import JudgeParseError
from fusion_first.model.providers.claude_cli import ClaudeCliUnavailable, PaidAuthRefused
from fusion_first.model.providers.ollama import OllamaUnavailable
from fusion_first.model.replay import CassetteMiss
from fusion_first.security.budget import BudgetExceeded, ModelNotAllowed


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc",
    [
        JudgeParseError("bad"),
        TimeoutError(),
        ProviderTimeout("slow"),
        ProviderRateLimited("429"),
        PromptTooLong("too long"),
        ClaudeCliUnavailable("exit 1"),
        OllamaUnavailable("down"),
    ],
)
def test_single_case_failures_are_isolatable(exc):
    assert isolatable(exc)


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc",
    [
        CassetteMiss("stale"),
        BudgetExceeded("cap"),
        ModelNotAllowed("nope"),
        ProviderQuotaExhausted("usage limit"),
        PaidAuthRefused("api key"),
        RuntimeError("unknown bug"),
        KeyError("x"),
    ],
)
def test_run_level_failures_are_not_isolatable(exc):
    assert not isolatable(exc)


@pytest.mark.unit
def test_quota_exhausted_is_fatal_and_never_retryable():
    e = ProviderQuotaExhausted("usage limit reached", resets_at="3pm")
    assert isinstance(e, FatalRunError)
    assert e.retryable is False
    assert e.resets_at == "3pm"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exc", "stage", "kind"),
    [
        (JudgeParseError("x"), "judge", ErrorKind.JUDGE_PARSE),
        (TimeoutError(), "judge", ErrorKind.JUDGE_TIMEOUT),
        (TimeoutError(), "target", ErrorKind.TARGET_TIMEOUT),
        (OllamaUnavailable("down"), "target", ErrorKind.TARGET_ERROR),
        (ClaudeCliUnavailable("exit"), "judge", ErrorKind.JUDGE_ERROR),
        (ProviderRateLimited("429"), "judge", ErrorKind.RATE_LIMITED),
        (ProviderQuotaExhausted("limit"), "target", ErrorKind.QUOTA_EXHAUSTED),
        (PromptTooLong("big"), "target", ErrorKind.PROMPT_TOO_LONG),
        (BudgetExceeded("cap"), "judge", ErrorKind.BUDGET_EXCEEDED),
        (CassetteMiss("k"), "judge", ErrorKind.CASSETTE_MISS),
        (ModelNotAllowed("m"), "target", ErrorKind.MODEL_NOT_ALLOWED),
        (PaidAuthRefused("key"), "judge", ErrorKind.AUTH_REFUSED),
        (RuntimeError("?"), "judge", ErrorKind.INTERNAL),
    ],
)
def test_classify(exc, stage, kind):
    assert classify(exc, stage) == kind
