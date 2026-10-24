BEGIN;

-- 最近一次觸發失敗的原因與時間；觸發成功時清掉
ALTER TABLE workflow_schedules
ADD COLUMN IF NOT EXISTS last_error TEXT;

ALTER TABLE workflow_schedules
ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMP;

COMMIT;