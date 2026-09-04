from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.db import get_db
from app.models.task import Task, TaskStatus
from app.models.runner import Runner
from app.schemas.runner import RunnerTaskResponse, RunnerTaskComplete
from app.core.security import get_current_runner
from app.tasks.executor import record_task_success, record_task_failure

# 注意：這裡刻意不掛 app.core.rate_limit.RateLimiter——它內部寫死用 get_current_user
# 認證（要有 JWT），但 agent 只有 runner token，掛了會讓每個請求都變成 401。
# 這個路由本身已經受 runner token 保護，不對外公開。
router = APIRouter(
    prefix="/runner",
    tags=["Runner Agent"],
)


@router.get("/tasks/next", response_model=Optional[RunnerTaskResponse])
def claim_next_task(
    db: Session = Depends(get_db),
    runner: Runner = Depends(get_current_runner),
):
    """本機 agent 輪詢用：認領下一個指派給這個 runner、且已到執行時間的 task。
    沒有可認領的 task 就回傳 null（200），agent 過一陣子再問一次。"""
    now = datetime.utcnow()
    task = db.scalars(
        select(Task)
        .where(
            Task.runner_id == runner.id,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.RETRYING]),
            or_(Task.scheduled_at.is_(None), Task.scheduled_at <= now),
        )
        .order_by(Task.priority.desc(), Task.created_at.asc())
    ).first()

    if not task:
        return None

    task.status = TaskStatus.RUNNING
    db.commit()
    db.refresh(task)
    return task


@router.post("/tasks/{task_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_task(
    task_id: UUID,
    payload: RunnerTaskComplete,
    db: Session = Depends(get_db),
    runner: Runner = Depends(get_current_runner),
):
    """本機 agent 執行完（成功或失敗）之後回報結果，走跟 Celery worker 一樣的
    TaskLog / advance_workflow / 重試邏輯（見 app.tasks.executor）。"""
    task = db.get(Task, task_id)
    if not task or task.runner_id != runner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is currently '{task.status}', not running",
        )

    if payload.status == "success":
        record_task_success(db, task, payload.result)
    else:
        record_task_failure(db, task, payload.error or "Unknown error reported by runner")

    return None
