CREATE TABLE IF NOT EXISTS task_messages (
    id         UUID PRIMARY KEY,
    task_id    UUID        NOT NULL,
    role       TEXT        NOT NULL,
    content    TEXT        NOT NULL,
    meta       JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_task_messages_task_id    ON task_messages (task_id);
CREATE INDEX IF NOT EXISTS ix_task_messages_created_at ON task_messages (created_at);
