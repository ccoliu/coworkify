from datetime import datetime
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.schedule import WorkflowSchedule
from app.models.user import User
from app.schemas.schedule import WorkflowScheduleCreate, WorkflowScheduleUpdate, WorkflowScheduleResponse
from app.core.security import get_current_user
from app.core.rate_limit import RateLimiter
from app.core.cron import compute_next_run
from sqlalchemy import select

router = APIRouter(
    prefix="/schedules",
    tags=["Schedules"],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))]
)

@router.post("/", response_model=WorkflowScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: WorkflowScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    schedule = WorkflowSchedule(
        name = payload.name,
        cron_expression = payload.cron_expression,
        steps = [s.model_dump() for s in payload.steps],
        enabled = payload.enabled,
        created_by = current_user.id,
        next_run_at=compute_next_run(payload.cron_expression, datetime.utcnow())
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule

@router.get("/", response_model=List[WorkflowScheduleResponse])
def list_schedules(db: Session = Depends(get_db)):
    schedules = db.scalars(select(WorkflowSchedule).order_by(WorkflowSchedule.created_at.desc())).all()
    return schedules
    
@router.get("/{schedule_id}",  response_model=WorkflowScheduleResponse)
def get_schedule(schedule_id:UUID, db:Session=Depends(get_db)):
    schedule=db.get(WorkflowSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return schedule

@router.patch("/{schedule_id}", response_model=WorkflowScheduleResponse)
def update_schedule(
    schedule_id:UUID,
    payload: WorkflowScheduleUpdate,
    db:Session=Depends(get_db),
):
    schedule = db.get(WorkflowSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if payload.name is not None:
        schedule.name = payload.name
    if payload.steps is not None:
        schedule.steps = [s.model_dump() for s in payload.steps]
    if payload.cron_expression is not None:
        schedule.cron_expression = payload.cron_expression
        schedule.next_run_at = compute_next_run(payload.cron_expression, datetime.utcnow())
    if payload.enabled is not None:
        schedule.enabled = payload.enabled

    db.commit()
    db.refresh(schedule)
    return schedule

@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id:UUID, db:Session=Depends(get_db)):
    schedule = db.get(WorkflowSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    db.delete(schedule)
    db.commit()
    return None