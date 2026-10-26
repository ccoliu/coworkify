-- 每個資源都屬於建立它的使用者。執行時指定「沒有擁有者的舊資料」要歸給誰：
--   psql -v owner=coworkify -f 2026_10_26_owners.sql
-- 指定的使用者不存在時整個 migration 失敗（ROLLBACK），不會留下一半。
\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE workflows ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users (id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users (id);
CREATE INDEX IF NOT EXISTS ix_workflows_created_by ON workflows (created_by);
CREATE INDEX IF NOT EXISTS ix_tasks_created_by ON tasks (created_by);

CREATE TEMP TABLE legacy_owner ON COMMIT DROP AS
SELECT id FROM users WHERE username = :'owner';

DO $$
BEGIN
    IF (SELECT count(*) FROM legacy_owner) <> 1 THEN
        RAISE EXCEPTION 'owner user not found — pass it with -v owner=<username>';
    END IF;
END $$;

-- 1. 沒有擁有者的定義與排程 → 指定的使用者
UPDATE workflow_definitions SET created_by = (SELECT id FROM legacy_owner) WHERE created_by IS NULL;
UPDATE workflow_schedules SET created_by = (SELECT id FROM legacy_owner) WHERE created_by IS NULL;

-- 2. run 跟著它的定義走；沒有定義的一次性 run → 指定的使用者
UPDATE workflows w SET created_by = d.created_by
FROM workflow_definitions d
WHERE w.definition_id = d.id AND w.created_by IS NULL;
UPDATE workflows SET created_by = (SELECT id FROM legacy_owner) WHERE created_by IS NULL;

-- 3. task 跟著它所在的 run 走；單獨建立的 task → 指定的使用者
UPDATE tasks t SET created_by = w.created_by
FROM workflow_steps s JOIN workflows w ON w.id = s.workflow_id
WHERE s.task_id = t.id AND t.created_by IS NULL;
UPDATE tasks SET created_by = (SELECT id FROM legacy_owner) WHERE created_by IS NULL;

COMMIT;
