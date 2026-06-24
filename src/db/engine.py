"""
Async database engine — SQLite (dev) / PostgreSQL (prod).

Usage:
    await init_db()                               # Uses DATABASE_URL env or SQLite default
    await init_db("sqlite+aiosqlite:///:memory:")  # In-memory for tests
    async for session in get_db(): ...             # FastAPI dependency
    await close_db()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "medical_records.db"
_DEFAULT_URL = f"sqlite+aiosqlite:///{_DEFAULT_DB_PATH}"

_engine: AsyncEngine | None = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None


def create_async_engine_from_url(url: str) -> AsyncEngine:
    if not url:
        raise ValueError("DATABASE_URL must not be empty")
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_recycle"] = 1800
    return create_async_engine(url, echo=False, **kwargs)


def async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(url: str | None = None) -> None:
    global _engine, _SessionLocal
    if url is None:
        url = os.environ.get("DATABASE_URL", _DEFAULT_URL)
    _engine = create_async_engine_from_url(url)
    _SessionLocal = async_session_factory(_engine)
    from src.db.models import Base
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine, _SessionLocal
    if _engine:
        await _engine.dispose()
    _engine = None
    _SessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if _SessionLocal is None:
        await init_db()
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
