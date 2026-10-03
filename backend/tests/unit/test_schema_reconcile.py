"""Additive schema reconciliation.

This code writes ALTER TABLE against the live database at startup, so what it
refuses to do matters as much as what it does.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, Text, func
from sqlalchemy.dialects import postgresql

from src.core.db import _column_ddl

PG = postgresql.dialect()


def ddl(column: Column) -> str | None:
    return _column_ddl(column, PG)


def test_a_nullable_column_is_added_plainly():
    assert ddl(Column("note", Text, nullable=True)) == "note TEXT"


def test_a_not_null_column_carries_its_default_to_the_server():
    """`default=` is applied in Python on insert, so it does nothing for rows
    that already exist — and those are the only rows this ever runs against."""
    assert ddl(Column("remind", Boolean, default=True, nullable=False)) == (
        "remind BOOLEAN NOT NULL DEFAULT true"
    )
    assert ddl(Column("flag", Boolean, default=False, nullable=False)) == (
        "flag BOOLEAN NOT NULL DEFAULT false"
    )
    assert ddl(Column("count", Integer, default=0, nullable=False)) == (
        "count INTEGER NOT NULL DEFAULT 0"
    )


def test_a_string_default_is_quoted_and_escaped():
    assert ddl(Column("source", Text, default="manual", nullable=False)) == (
        "source TEXT NOT NULL DEFAULT 'manual'"
    )
    assert "''" in (ddl(Column("s", Text, default="it's", nullable=False)) or "")


def test_a_not_null_column_with_no_default_is_added_nullable_instead():
    """Guessing a backfill value is worse than a nullable column."""
    out = ddl(Column("mystery", Text, nullable=False))
    assert out == "mystery TEXT"
    assert "NOT NULL" not in out


def test_a_callable_default_is_added_nullable_instead():
    """func.now() cannot be rendered as a literal for existing rows."""
    out = ddl(Column("seen_at", DateTime(timezone=True), default=func.now, nullable=False))
    assert "NOT NULL" not in out


def test_an_existing_server_default_is_trusted():
    column = Column("created", DateTime(timezone=True), server_default=func.now(), nullable=False)
    assert ddl(column) == "created TIMESTAMP WITH TIME ZONE NOT NULL"


def test_the_commitments_model_would_produce_the_column_that_was_missing():
    """The exact failure a sibling agent hit: `column "remind" ... does not exist`."""
    from src.models.commitment import CommitmentDB

    remind = CommitmentDB.__table__.columns["remind"]
    assert ddl(remind) == "remind BOOLEAN NOT NULL DEFAULT true"
