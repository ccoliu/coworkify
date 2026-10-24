BEGIN;

-- 認領（claim）時間：recover_stale_tasks 用它找出 worker 已經不在、卻停在 RUNNING 的 task
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP;

-- 回收時只掃 RUNNING 的那一小撮，不必整張表掃
CREATE INDEX IF NOT EXISTS ix_tasks_running_claimed_at ON tasks (claimed_at)
WHERE
    status = 'running';

COMMIT;