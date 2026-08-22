from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ..core.config import get_settings
from ..core.logging import get_logger

logger = get_logger("core.db")


class Base(DeclarativeBase):
    pass


_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _build_engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
        connect_args={
            "server_settings": {"jit": "off"},
        },
    )


def init_db(database_url: Optional[str] = None) -> bool:
    global _engine, _session_factory
    settings = get_settings()
    url = database_url or settings.database_url
    if not url:
        logger.warning("database_url_unset_skipping_db_init")
        return False
    try:
        _engine = _build_engine(url)
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info("database_initialized")
        return True
    except Exception as exc:
        logger.error("database_init_failed", error=str(exc))
        _engine = None
        _session_factory = None
        return False


def is_db_available() -> bool:
    return _engine is not None and _session_factory is not None


async def create_all_tables() -> None:
    if not is_db_available():
        logger.warning("database_not_available_skipping_create_all")
        return
    assert _engine is not None
    async with _engine.begin() as conn:
        from ..models.knowledge import KnowledgeCrystalDB
        from ..models.task import TaskDB
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if not is_db_available():
        raise RuntimeError(
            "Database not initialized. Set DATABASE_URL and call init_db() first."
        )
    assert _session_factory is not None
    session: AsyncSession = _session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception as exc:
            logger.warning("database_dispose_warning", error=str(exc))
    _engine = None
    _session_factory = None
