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
        # Imported for the side effect of registering each table on
        # Base.metadata before create_all runs.
        from ..models.commitment import CommitmentDB  # noqa: F401
        from ..models.conversation import TaskMessageDB  # noqa: F401
        from ..models.day_block import DayBlockStateDB  # noqa: F401
        from ..models.knowledge import KnowledgeCrystalDB  # noqa: F401
        from ..models.task import TaskDB  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    logger.info("database_tables_created")


def _column_ddl(column, dialect) -> Optional[str]:
    """`ADD COLUMN` for one column, or None when it cannot be done safely.

    A NOT NULL column cannot be added to a table that already has rows unless
    a server default comes with it. SQLAlchemy's `default=` is applied in
    Python on insert, so it does nothing for rows that already exist — which is
    exactly the case here, since this only runs for columns that were added to
    a model after the table was created.

    So a scalar Python default is promoted to a server default. Anything else
    (a callable, or no default at all) is added nullable instead, because
    guessing a backfill value is worse than a nullable column.
    """
    type_sql = column.type.compile(dialect)
    if column.nullable or column.server_default is not None:
        null_sql = "" if column.nullable else " NOT NULL"
        return f"{column.name} {type_sql}{null_sql}"

    default = getattr(column.default, "arg", None)
    if column.default is None or callable(default):
        logger.warning(
            "schema_column_added_nullable",
            column=column.name,
            reason="NOT NULL without a scalar default cannot be backfilled safely",
        )
        return f"{column.name} {type_sql}"

    if isinstance(default, bool):
        literal = "true" if default else "false"
    elif isinstance(default, (int, float)):
        literal = str(default)
    elif isinstance(default, str):
        escaped = default.replace("'", "''")
        literal = f"'{escaped}'"
    else:
        logger.warning("schema_column_added_nullable", column=column.name,
                       reason=f"unrenderable default {type(default).__name__}")
        return f"{column.name} {type_sql}"

    return f"{column.name} {type_sql} NOT NULL DEFAULT {literal}"


def _add_missing_columns(conn) -> None:
    """Add columns a model declares that the live table does not have.

    create_all() creates missing TABLES and nothing else — it will not touch a
    table that already exists. So any column added to a model after its first
    deploy silently never reaches the database, and the failure surfaces much
    later as an INSERT blowing up on a column that does not exist. That is how
    `remind` reached production missing: a sibling agent got
    `column "remind" of relation "commitments" does not exist` and could not
    file anything at all.

    Deliberately additive only. Dropping or retyping a column is destructive
    and is reported rather than performed.
    """
    from sqlalchemy import inspect as sa_inspect, text as sa_text

    inspector = sa_inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all just made it, so it matches by construction
        live = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in live:
                continue
            ddl = _column_ddl(column, conn.dialect)
            if ddl is None:
                continue
            conn.execute(sa_text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))
            logger.warning("schema_column_added", table=table.name, column=column.name, ddl=ddl)

        unknown = live - {c.name for c in table.columns}
        if unknown:
            # Never dropped: a column this code does not know about may be one
            # an older version still writes to.
            logger.info("schema_columns_not_in_model", table=table.name, columns=sorted(unknown))


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
