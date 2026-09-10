-- Per-day completion for timetable blocks. The template is a matrix sheet whose
-- cells are shared across all seven weekdays, so per-day state cannot live there.
CREATE TABLE IF NOT EXISTS day_block_state (
    id         UUID PRIMARY KEY,
    day        DATE        NOT NULL,
    slot       TEXT        NOT NULL,
    label      TEXT        NOT NULL,
    done_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_day_block UNIQUE (day, slot, label)
);
CREATE INDEX IF NOT EXISTS ix_day_block_state_day ON day_block_state (day);
