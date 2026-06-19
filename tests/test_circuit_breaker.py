"""Tests for the circuit breaker pattern."""

import time

import pytest

from src.llm.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def test_circuit_starts_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == CircuitState.CLOSED


def test_success_keeps_circuit_closed():
    cb = CircuitBreaker(failure_threshold=3)
    result = cb.call(lambda: "ok")
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, timeout=1)

    def failing():
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(failing)

    assert cb.state == CircuitState.OPEN

    with pytest.raises(CircuitOpenError):
        cb.call(failing)


def test_failures_below_threshold_stay_closed():
    cb = CircuitBreaker(failure_threshold=3)

    def failing():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(failing)

    assert cb.state == CircuitState.CLOSED


def test_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=3)

    def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        cb.call(failing)
    with pytest.raises(RuntimeError):
        cb.call(failing)

    assert cb.failure_count == 2

    cb.call(lambda: "ok")
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


def test_circuit_recovers_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, timeout=1, success_threshold=1)
    call_count = 0

    def sometimes_fails():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("fail")
        return "recovered"

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(sometimes_fails)

    assert cb.state == CircuitState.OPEN

    time.sleep(1.1)

    result = cb.call(sometimes_fails)
    assert result == "recovered"
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens_circuit():
    cb = CircuitBreaker(failure_threshold=2, timeout=1, success_threshold=1)

    def always_fails():
        raise RuntimeError("still broken")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(always_fails)

    assert cb.state == CircuitState.OPEN

    time.sleep(1.1)

    with pytest.raises(RuntimeError):
        cb.call(always_fails)

    assert cb.state == CircuitState.OPEN


def test_reset():
    cb = CircuitBreaker(failure_threshold=2)

    def failing():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(failing)

    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_get_state():
    cb = CircuitBreaker(name="test-cb", failure_threshold=3)
    state = cb.get_state()
    assert state["name"] == "test-cb"
    assert state["state"] == "closed"
    assert state["failure_count"] == 0
    assert state["last_failure"] is None
