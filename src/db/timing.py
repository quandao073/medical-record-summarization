"""Query timing utility for database performance measurement."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

logger = logging.getLogger("db.timing")


@asynccontextmanager
async def timed_query(name: str):
    """Async context manager that logs query execution time.

    Usage:
        async with timed_query("load_patient_P001"):
            result = await session.execute(stmt)
    """
    start = time.perf_counter()
    yield
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("Query %s: %.1fms", name, duration_ms)
