"""Tests for database fault tolerance: pool_pre_ping and startup retry/backoff."""

import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import OperationalError


class TestEnginePoolConfig:
    def test_sqlite_engine_has_pre_ping(self):
        from src.db.engine import create_async_engine_from_url
        engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
        assert engine.pool._pre_ping is True

    def test_postgres_engine_has_pre_ping_and_recycle(self):
        pytest.importorskip("asyncpg")
        from src.db.engine import create_async_engine_from_url
        engine = create_async_engine_from_url(
            "postgresql+asyncpg://app:pw@localhost:5432/medical_records"
        )
        assert engine.pool._pre_ping is True
        assert engine.pool._recycle == 1800


class TestInitDbRetry:
    @pytest.mark.asyncio
    async def test_succeeds_first_attempt_no_sleep(self):
        from api.main import _init_db_with_retry

        with patch("src.db.engine.init_db", new=AsyncMock()) as mock_init, \
             patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await _init_db_with_retry(max_attempts=5, base_delay=0.01)

        mock_init.assert_awaited_once()
        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        from api.main import _init_db_with_retry

        mock_init = AsyncMock(
            side_effect=[OperationalError("conn failed", None, BaseException()), None]
        )
        with patch("src.db.engine.init_db", new=mock_init), \
             patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await _init_db_with_retry(max_attempts=5, base_delay=0.01)

        assert mock_init.await_count == 2
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        from api.main import _init_db_with_retry

        mock_init = AsyncMock(
            side_effect=OperationalError("conn failed", None, BaseException())
        )
        with patch("src.db.engine.init_db", new=mock_init), \
             patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(OperationalError):
                await _init_db_with_retry(max_attempts=3, base_delay=0.01)

        assert mock_init.await_count == 3
