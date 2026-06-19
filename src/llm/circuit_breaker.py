"""Circuit breaker pattern for LLM API calls.

Prevents hammering a failing API with retries.  Three states:
  CLOSED     – normal operation, all calls pass through
  OPEN       – too many failures, reject calls immediately
  HALF_OPEN  – testing whether the service has recovered
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from threading import Lock


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is open and calls are being rejected."""


class CircuitBreaker:

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        success_threshold: int = 2,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.name = name

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: datetime | None = None
        self.state = CircuitState.CLOSED
        self._lock = Lock()

    def call(self, func, *args, **kwargs):
        """Execute *func* with circuit-breaker protection."""
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is OPEN. "
                        f"Last failure: {self.last_failure_time}. "
                        f"Will retry after {self.timeout}s."
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    # ------------------------------------------------------------------

    def _on_success(self) -> None:
        with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.success_count = 0

    def _on_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        if not self.last_failure_time:
            return True
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.timeout

    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Manually reset the circuit (admin / testing)."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure": (
                self.last_failure_time.isoformat() if self.last_failure_time else None
            ),
        }
