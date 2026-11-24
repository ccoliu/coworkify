BEGIN;

-- 使用者標成常用的定義：建構器的 Workflows 選單先載入這些，其他的要用時才抓
ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN NOT NULL DEFAULT false;

COMMIT;
