from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import session
from sqlalchemy import delete, select

from app.db import get_db
from app.models.task import Task, TaskStatus
from app.models.task_log import TaskLog
from app.models.workflow import WorkflowStep, WorkflowStepTemplate
from app.schemas.task import TaskCreate, TaskResponse, TaskResultResponse
from app.tasks.executor import execute_task, dispatch_task, queue_for_task_type
from app.core.security import get_current_user
from app.core.rate_limit import RateLimiter

router = APIRouter(prefix="/tasks", tags=["Tasks"], dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))])

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task_in: TaskCreate, db: session = Depends(get_db)):
    db_task = Task(
        name = task_in.name,
        task_type = task_in.task_type,
        payload = task_in.payload,
        priority = task_in.priority,
        max_retries = task_in.max_retries,
        scheduled_at = task_in.scheduled_at,
        status = "pending",
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    if db_task.scheduled_at:
        # 指定時間執行
        execute_task.apply_async(
            args=[str(db_task.id)],
            eta=db_task.scheduled_at,
            priority=db_task.priority,
            queue=queue_for_task_type(db_task.task_type),
        )
    else:
        # 立即執行
        dispatch_task(db_task)

    return db_task

# 取得所有任務
@router.get("/", response_model=List[TaskResponse])
def get_tasks(
    status: Optional[str] = Query(None, description="任務狀態(pending/running/success/failed)"),
    task_type: Optional[str] = Query(None, description="任務類型"),
    limit: int = Query(20, ge=1, le=100, description="每頁筆數"),
    offset: int = Query(0, ge=0, description="跳過筆數"),
    db: session = Depends(get_db)
):
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    if task_type:
        stmt = stmt.where(Task.task_type == task_type)
    stmt = stmt.order_by(Task.created_at.desc(), Task.priority.desc()).limit(limit).offset(offset)
    tasks = db.scalars(stmt).all()
    return tasks

@router.get("/{task_id}", response_model=TaskResponse)
def get_task_by_id(task_id: UUID, db: session = Depends(get_db)):
    stmt = select(Task).where(Task.id == task_id)
    task = db.scalars(stmt).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task

@router.get("/{task_id}/result", response_model=TaskResultResponse)
def get_task_result(task_id: UUID, db: session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    log = db.scalars(
        select(TaskLog).where(TaskLog.task_id == task_id).order_by(TaskLog.created_at.desc())
    ).first()

    return TaskResultResponse(
        task_id=task_id,
        status=task.status,
        result=log.result if log else None,
        error_message=log.error_message if log else None,
    )

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: UUID, db: session = Depends(get_db)):
    stmt = select(Task).where(Task.id == task_id)
    task = db.scalars(stmt).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # WorkflowStep.task_id / WorkflowStepTemplate.for_each_task_id are FKs to
    # tasks.id with no ON DELETE CASCADE — deleting a task that's part of a
    # workflow used to hit an unhandled DB IntegrityError (500). There is
    # also currently no way to delete a whole workflow (which would need to
    # clean up its tasks too), so this stays a clear refusal rather than a
    # silent cascade that could leave a workflow with missing steps.
    in_workflow = db.scalars(
        select(WorkflowStep.id).where(WorkflowStep.task_id == task_id)
    ).first() or db.scalars(
        select(WorkflowStepTemplate.id).where(WorkflowStepTemplate.for_each_task_id == task_id)
    ).first()
    if in_workflow is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This task is part of a workflow and can't be deleted on its own.",
        )

    # TaskLog.task_id is the same kind of FK, but its rows are just this
    # task's own execution history — nothing else references them, so unlike
    # a workflow they're safe (and correct) to delete along with the task
    # instead of refusing. Without this, virtually no task could ever be
    # deleted: even a single instantly-completed run already writes one.
    db.execute(delete(TaskLog).where(TaskLog.task_id == task_id))
    db.delete(task)
    db.commit()
    return None
    

    
    