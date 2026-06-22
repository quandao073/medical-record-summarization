import pytest
from src.llm.retry import retry_with_backoff
from src.llm.errors import LLMConnectionError


def test_retry_succeeds_after_failures():
    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise LLMConnectionError("connection refused")
        return "success"

    result = retry_with_backoff(flaky, max_retries=3, base_delay=0.01)
    assert result == "success"
    assert call_count == 3


def test_retry_raises_after_max_retries():
    def always_fails():
        raise LLMConnectionError("always fails")

    with pytest.raises(LLMConnectionError):
        retry_with_backoff(always_fails, max_retries=2, base_delay=0.01)


def test_retry_does_not_retry_non_retryable():
    call_count = 0

    def value_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        retry_with_backoff(
            value_error,
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(LLMConnectionError,),
        )
    assert call_count == 1


def test_no_retry_on_success():
    call_count = 0

    def ok():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = retry_with_backoff(ok, max_retries=3, base_delay=0.01)
    assert result == "ok"
    assert call_count == 1


def test_retry_with_timeout_error():
    call_count = 0

    def timeout():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TimeoutError("timed out")
        return "recovered"

    result = retry_with_backoff(timeout, max_retries=3, base_delay=0.01)
    assert result == "recovered"
    assert call_count == 2
