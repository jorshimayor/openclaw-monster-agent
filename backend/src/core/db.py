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


def normalize_database_url(url: str) -> tuple[str, bool]:
    """(clean_url, ssl_required) for the async engine.

    - postgres:// and postgresql:// become postgresql+asyncpg:// — the
      SQLAlchemy ASYNC engine refuses the bare schemes (it loads the sync
      psycopg2 dialect and raises). Without this, init_db failed silently in
      production and every task write no-op'd.
    - sslmode / channel_binding are libpq-only query params asyncpg rejects;
      sslmode becomes explicit ssl connect_args, both are stripped.
    """
    import re

    url = url.strip().strip('"').strip("'")
    # A whole .env line pasted as the secret value ("DATABASE_URL=postgres…")
    # — main.py's diag strips this for DISPLAY only, which masked a dead
    # engine in production. Strip it for real.
    if re.match(r"(?i)^database_url=", url):
        url = url.split("=", 1)[1].strip().strip('"').strip("'")

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    ssl_flag = "sslmode=require" in url or "sslmode=verify" in url
    clean_url = re.sub(r"[?&]sslmode=[^&]+", "", url)
    clean_url = re.sub(r"[?&]channel_binding=[^&]+", "", clean_url)
    # Stripping the first param can orphan the rest ("db&a=b") or leave a
    # dangling separator — restore a well-formed query string.
    if "?" not in clean_url and "&" in clean_url:
        clean_url = clean_url.replace("&", "?", 1)
    clean_url = re.sub(r"\?&", "?", clean_url)
    clean_url = re.sub(r"[?&]$", "", clean_url)
    return clean_url, ssl_flag


def _build_engine(url: str) -> AsyncEngine:
    clean_url, ssl_flag = normalize_database_url(url)

    connect_args: dict = {"server_settings": {"jit": "off"}}
    if ssl_flag:
        try:
            import ssl as _ssl
            try:
                import certifi  # type: ignore
                cafile = certifi.where()
            except Exception:
                cafile = None
            ctx = _ssl.create_default_context(
                purpose=_ssl.Purpose.SERVER_AUTH,
                cafile=cafile,
            )
            ctx.check_hostname = True
            ctx.verify_mode = _ssl.CERT_REQUIRED
            connect_args["ssl"] = ctx
        except Exception:
            connect_args["ssl"] = "require"
    return create_async_engine(
        clean_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
        connect_args=connect_args,
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
