from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import session
from sqlalchemy import select

from app.db import get_db
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate, TaskResponse
from app.tasks.executor import execute_task
from app.core.security import verify_api_key
from app.core.rate_limit import RateLimiter

router = APIRouter(prefix="/tasks", tags=["Tasks"], dependencies=[Depends(verify_api_key), Depends(RateLimiter(times=5000, seconds=1))])

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
        execute_task.apply_async(args=[str(db_task.id)], eta=db_task.scheduled_at, priority=db_task.priority) 
    else:
        # 立即執行
        execute_task.apply_async(args=[str(db_task.id)], priority=db_task.priority)

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
    stmt = stmt.order_by(Task.priority.desc()).limit(limit).offset(offset)
    tasks = db.scalars(stmt).all()
    return tasks

@router.get("/{task_id}", response_model=TaskResponse)
def get_task_by_id(task_id: UUID, db: session = Depends(get_db)):
    stmt = select(Task).where(Task.id == task_id)
    task = db.scalars(stmt).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: UUID, db: session = Depends(get_db)):
    stmt = select(Task).where(Task.id == task_id)
    task = db.scalars(stmt).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    db.delete(task)
    db.commit()
    return None
    

    
    