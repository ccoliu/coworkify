BEGIN;

-- webhook 觸發器（issue #9 phase 1）
CREATE TABLE IF NOT EXISTS workflow_triggers (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    definition_id UUID NOT NULL REFERENCES workflow_definitions (id) ON DELETE CASCADE,
    encrypted_secret TEXT NOT NULL,
    input_mapping JSON NOT NULL DEFAULT '{}',
    filter JSON NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID NOT NULL REFERENCES users (id),
    last_triggered_at TIMESTAMP,
    last_error TEXT,
    last_error_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_workflow_triggers_definition_id ON workflow_triggers (definition_id);

CREATE INDEX IF NOT EXISTS ix_workflow_triggers_created_by ON workflow_triggers (created_by);

-- run 怎麼開始的；舊資料留 NULL
ALTER TABLE workflows
ADD COLUMN IF NOT EXISTS trigger_kind VARCHAR(20);

ALTER TABLE workflows ADD COLUMN IF NOT EXISTS trigger_id UUID;

ALTER TABLE workflows
ADD COLUMN IF NOT EXISTS trigger_delivery_id VARCHAR(200);

-- 同一個 delivery 只建一次 run（GitHub 會重送）。有 NULL 的列不受限制。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_workflows_trigger_delivery') THEN
        ALTER TABLE workflows
            ADD CONSTRAINT uq_workflows_trigger_delivery UNIQUE (trigger_id, trigger_delivery_id);
    END IF;
END $$;

COMMIT;