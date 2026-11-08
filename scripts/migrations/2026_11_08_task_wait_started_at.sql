BEGIN;

-- sensor（wait_for）第一次檢查的時間：判斷等了多久、有沒有超過 timeout_seconds
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS wait_started_at TIMESTAMP;

-- recover_stale_tasks 會找「該檢查了卻沒人檢查」的 WAITING task，只掃那一小撮
CREATE INDEX IF NOT EXISTS ix_tasks_waiting_scheduled_at ON tasks (scheduled_at)
WHERE
    status = 'waiting';

COMMIT;
