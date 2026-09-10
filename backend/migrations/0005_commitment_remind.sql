-- Tracked-but-silent commitments. Bulk study picks belong on the day view
-- without producing a reminder each; only the core work interrupts.
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS remind BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS ix_commitments_open_remind
    ON commitments (due_at) WHERE status = 'open' AND remind;
