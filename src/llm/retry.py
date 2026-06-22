"""Retry with exponential backoff for LLM API calls."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from .errors import LLMConnectionError

T = TypeVar("T")

DEFAULT_RETRYABLE = (LLMConnectionError, TimeoutError, ConnectionError)


def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple[type[Exception], ...] = DEFAULT_RETRYABLE,
    **kwargs,
) -> T:
    last_exception: Exception | None = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                time.sleep(delay)
        except Exception:
            raise
    raise last_exception  # type: ignore[misc]
