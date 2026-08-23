"""Regression tests for database URL normalization.

The bare `postgresql://` scheme made create_async_engine raise, init_db
swallowed it, and production task persistence silently no-op'd for weeks.
"""

from __future__ import annotations

from src.core.db import normalize_database_url


def test_neon_url_full_form():
    url, ssl = normalize_database_url(
        "postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    assert url == "postgresql+asyncpg://u:p@ep-x.aws.neon.tech/neondb"
    assert ssl is True


def test_heroku_style_postgres_scheme():
    url, ssl = normalize_database_url("postgres://u:p@host/db?sslmode=require")
    assert url == "postgresql+asyncpg://u:p@host/db"
    assert ssl is True


def test_plain_url_gets_async_driver():
    url, ssl = normalize_database_url("postgresql://u:p@host/db")
    assert url == "postgresql+asyncpg://u:p@host/db"
    assert ssl is False


def test_already_async_url_untouched_except_params():
    url, ssl = normalize_database_url(
        "postgresql+asyncpg://u:p@host/db?channel_binding=require"
    )
    assert url == "postgresql+asyncpg://u:p@host/db"
    assert ssl is False


def test_pasted_env_line_prefix_stripped():
    # The production pathology: the whole .env line pasted as the secret.
    url, ssl = normalize_database_url(
        'DATABASE_URL="postgresql://u:p@ep-x.neon.tech/neondb?sslmode=require"'
    )
    assert url == "postgresql+asyncpg://u:p@ep-x.neon.tech/neondb"
    assert ssl is True


def test_other_query_params_survive():
    url, _ = normalize_database_url(
        "postgresql://u:p@host/db?sslmode=require&application_name=zc"
    )
    assert url == "postgresql+asyncpg://u:p@host/db?application_name=zc"
