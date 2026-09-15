BEGIN;

CREATE TABLE IF NOT EXISTS workflow_definitions (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    steps JSON NOT NULL,
    input_schema JSON NOT NULL DEFAULT '[]',
    version INTEGER NOT NULL DEFAULT 1,
    created_by UUID REFERENCES users (id),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_workflow_definitions_id ON workflow_definitions (id);

ALTER TABLE workflows
ADD COLUMN IF NOT EXISTS definition_id UUID REFERENCES workflow_definitions (id) ON DELETE SET NULL;

ALTER TABLE workflows
ADD COLUMN IF NOT EXISTS definition_version INTEGER;

ALTER TABLE workflows ADD COLUMN IF NOT EXISTS input JSON;

CREATE INDEX IF NOT EXISTS ix_workflows_definition_id ON workflows (definition_id);

-- Backfill: one definition per workflow name, using the newest run's template.
-- Scheduled runs are named "<schedule> @ YYYY-MM-DD HH:MM:SS"; strip the suffix
-- so every run of one schedule lands on the same definition.
WITH runs AS (
    SELECT id, created_at, steps_template,
           regexp_replace(name, ' @ \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', '') AS base_name
    FROM workflows
    WHERE steps_template IS NOT NULL AND definition_id IS NULL
), latest AS (
    SELECT DISTINCT ON (base_name) base_name, steps_template
    FROM runs
    ORDER BY base_name, created_at DESC
), inserted AS (
    INSERT INTO workflow_definitions (id, name, steps, input_schema, version, created_at, updated_at)
    SELECT gen_random_uuid(), base_name, steps_template, '[]'::json, 1, now(), now()
    FROM latest
    RETURNING id, name
)
UPDATE workflows w
SET definition_id = i.id, definition_version = 1
FROM runs r JOIN inserted i ON i.name = r.base_name
WHERE w.id = r.id;

COMMIT;