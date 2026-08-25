import time
import traceback
import uuid
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models.task import Task, TaskStatus
from app.models.task_log import TaskLog
from app.tasks.handler import get_task_handler, TASK_REGISTRY

@celery_app.task(bind=True, name="coworkify.execute_task")
def execute_task(self, task_id: str):
    db = SessionLocal()
    start_time = time.time()
    task_uuid = uuid.UUID(task_id)

    try:
        task = db.get(Task, task_uuid)
        if not task:
            return f"Task {task_uuid} not found"

        if task.status == TaskStatus.RUNNING or task.status == TaskStatus.SUCCESS or task.status == TaskStatus.FAILED:
            return f"Task {task_uuid} is already {task.status}"

        # 1. 更新狀態為 RUNNING (idempotent)
        task.status = TaskStatus.RUNNING if (task.status == TaskStatus.PENDING or task.status == TaskStatus.RETRYING) else task.status
       
        # 2. 尋找對應的 handler
        handler = get_task_handler(task.task_type)
        if not handler:
            raise ValueError(f"Unknown task type: {task.task_type}. Available types: {list(TASK_REGISTRY.keys())}")
        
        # 3. 記錄任務開始
        result = handler(task.payload)
        execute_time_ms = (time.time() - start_time) * 1000

        # 4. 執行成功
        task.status = TaskStatus.SUCCESS
        log = TaskLog(
            task_id=task.id,
            status=TaskStatus.SUCCESS,
            result=result,
            execution_time_ms=execute_time_ms
        )
        db.add(log)
        db.commit()
        return result

    except Exception as exc:
        execute_time_ms = (time.time() - start_time) * 1000
        task = db.get(Task, task_uuid)

        if task:
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.RETRYING
                countdown = 2 ** task.retry_count # Exponential Backoff
                
                log = TaskLog(
                    task_id=task.id,
                    status=TaskStatus.RETRYING,
                    error_message=f"Attempt {task.retry_count} failed: {str(exc)}. Retrying in {countdown}s...",
                    execution_time_ms=execute_time_ms
                )
                db.add(log)
                db.commit()
                db.close()

                raise self.retry(countdown=countdown, exc=exc)
            else:
                task.status = TaskStatus.FAILED
                log = TaskLog(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error_message=f"Maximum retries ({task.max_retries}) exceeded: {str(exc)}",
                    execution_time_ms=execute_time_ms
                )
                db.add(log)
                db.commit()
                db.close()
                
        raise exc
    finally:
        db.close()
        
        