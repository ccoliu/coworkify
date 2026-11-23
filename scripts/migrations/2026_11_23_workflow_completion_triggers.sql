BEGIN;

-- workflow 結束時觸發另一條 workflow（issue #9 phase 2）
ALTER TABLE workflow_triggers ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'webhook';

ALTER TABLE workflow_triggers
    ADD COLUMN IF NOT EXISTS source_definition_id UUID REFERENCES workflow_definitions (id) ON DELETE CASCADE;

ALTER TABLE workflow_triggers ADD COLUMN IF NOT EXISTS on_status VARCHAR(10);

-- workflow 觸發器沒有 secret
ALTER TABLE workflow_triggers ALTER COLUMN encrypted_secret DROP NOT NULL;

-- advance_workflow 每次有 run 結束都會用它查「有沒有人在等這條產線」
CREATE INDEX IF NOT EXISTS ix_workflow_triggers_source_definition_id ON workflow_triggers (source_definition_id);

-- 詳細頁用 "<上游 run id>:success|failed" 找下游 run
CREATE INDEX IF NOT EXISTS ix_workflows_trigger_delivery_id ON workflows (trigger_delivery_id);

COMMIT;
