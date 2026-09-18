BEGIN;

ALTER TABLE workflow_schedules ALTER COLUMN steps DROP NOT NULL;

ALTER TABLE workflow_schedules
ADD COLUMN IF NOT EXISTS definition_id UUID REFERENCES workflow_definitions (id) ON DELETE CASCADE;

ALTER TABLE workflow_schedules ADD COLUMN IF NOT EXISTS input JSON;

CREATE INDEX IF NOT EXISTS ix_workflow_schedules_definition_id ON workflow_schedules (definition_id);

COMMIT;