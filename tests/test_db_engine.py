"""Tests for database engine and session factory."""

import pytest
from sqlalchemy import text


class TestDatabaseEngine:
    def test_create_engine_sqlite(self):
        from src.db.engine import create_async_engine_from_url
        engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
        assert engine is not None
        assert "sqlite" in str(engine.url)

    def test_create_engine_empty_url_raises(self):
        from src.db.engine import create_async_engine_from_url
        with pytest.raises(ValueError):
            create_async_engine_from_url("")

    @pytest.mark.asyncio
    async def test_session_connects(self):
        from src.db.engine import create_async_engine_from_url, async_session_factory
        engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
        factory = async_session_factory(engine)
        async with factory() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self):
        from src.db.engine import init_db, close_db
        await init_db("sqlite+aiosqlite:///:memory:")
        await close_db()
