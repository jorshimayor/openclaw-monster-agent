-- Monster Agent · Initial schema for Neon Postgres
-- Run against your Neon DB:
--   psql "$NEON_DATABASE_URL" -f backend/migrations/0001_initial_schema.sql
-- Or on first app startup, create_all_tables() will create these if they don't exist.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

DO $$ BEGIN
    CREATE TYPE task_status_enum AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    status task_status_enum NOT NULL DEFAULT 'pending',
    plan JSONB,
    result JSONB,
    error_message TEXT,
    current_step VARCHAR(128),
    progress_pct INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_crystals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    entities TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    strategies TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    pitfalls TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    frameworks TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    summary TEXT,
    category VARCHAR(64),
    raw_extras JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_crystals_category ON knowledge_crystals(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_crystals_created_at ON knowledge_crystals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_crystals_source_task ON knowledge_crystals(source_task_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tasks_updated_at ON tasks;
CREATE TRIGGER trg_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
