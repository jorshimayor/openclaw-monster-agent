-- Commitments — the accountability ledger the assistant chases you about.
-- Idempotent: create_all_tables() also builds this on boot, so re-running is safe.

CREATE TABLE IF NOT EXISTS commitments (
    id                UUID PRIMARY KEY,
    title             TEXT        NOT NULL,
    detail            TEXT,
    source            TEXT        NOT NULL DEFAULT 'manual',
    task_id           UUID,
    status            TEXT        NOT NULL DEFAULT 'open',
    due_at            TIMESTAMPTZ NOT NULL,
    nag_interval_sec  INTEGER     NOT NULL DEFAULT 1800,
    nag_count         INTEGER     NOT NULL DEFAULT 0,
    escalation        INTEGER     NOT NULL DEFAULT 0,
    last_nagged_at    TIMESTAMPTZ,
    snooze_until      TIMESTAMPTZ,
    artifact_kind     TEXT,
    artifact_url      TEXT,
    artifact_text     TEXT,
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_commitments_status     ON commitments (status);
CREATE INDEX IF NOT EXISTS ix_commitments_due_at     ON commitments (due_at);
CREATE INDEX IF NOT EXISTS ix_commitments_task_id    ON commitments (task_id);
CREATE INDEX IF NOT EXISTS ix_commitments_created_at ON commitments (created_at);

-- The nag loop's hot query: open rows whose due time has passed.
CREATE INDEX IF NOT EXISTS ix_commitments_open_due
    ON commitments (due_at) WHERE status = 'open';
