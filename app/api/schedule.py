from datetime import datetime
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.schedule import WorkflowSchedule
from app.models.user import User
from app.models.workflow import WorkflowDefinition
from app.schemas.definition import resolve_run_input
from app.schemas.schedule import WorkflowScheduleCreate, WorkflowScheduleUpdate, WorkflowScheduleResponse
from app.core.security import get_current_user
from app.core.rate_limit import RateLimiter
from app.core.cron import compute_next_run

router = APIRouter(
    prefix="/schedules",
    tags=["Schedules"],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))]
)


def _get_definition_or_400(db: Session, definition_id: UUID) -> WorkflowDefinition:
    definition = db.get(WorkflowDefinition, definition_id)
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow definition not found"
        )
    return definition


def _resolve_input_or_422(definition: WorkflowDefinition, provided: dict) -> dict | None:
    """排程的 input 在存檔當下就檢查，錯誤才不會等到半夜觸發時才發現。"""
    if not definition.input_schema:
        if provided:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This definition declares no input_schema, so a run takes no input.",
            )
        return None
    try:
        return resolve_run_input(definition.input_schema, provided)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _attach_definitions(db: Session, schedules: list[WorkflowSchedule]) -> None:
    ids = [s.definition_id for s in schedules if s.definition_id]
    if not ids:
        return
    by_id = {
        d.id: d
        for d in db.scalars(select(WorkflowDefinition).where(WorkflowDefinition.id.in_(ids))).all()
    }
    for s in schedules:
        definition = by_id.get(s.definition_id) if s.definition_id else None
        if definition:
            s.definition_name = definition.name
            s.definition_version = definition.version


@router.post("/", response_model=WorkflowScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: WorkflowScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    definition = _get_definition_or_400(db, payload.definition_id)
    schedule = WorkflowSchedule(
        name=payload.name,
        cron_expression=payload.cron_expression,
        definition_id=definition.id,
        input=_resolve_input_or_422(definition, payload.input),
        enabled=payload.enabled,
        created_by=current_user.id,
        next_run_at=compute_next_run(payload.cron_expression, datetime.utcnow()),
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    _attach_definitions(db, [schedule])
    return schedule


@router.get("/", response_model=List[WorkflowScheduleResponse])
def list_schedules(db: Session = Depends(get_db)):
    schedules = db.scalars(select(WorkflowSchedule).order_by(WorkflowSchedule.created_at.desc())).all()
    _attach_definitions(db, schedules)
    return schedules


@router.get("/{schedule_id}", response_model=WorkflowScheduleResponse)
def get_schedule(schedule_id: UUID, db: Session = Depends(get_db)):
    schedule = db.get(WorkflowSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    _attach_definitions(db, [schedule])
    return schedule


@router.patch("/{schedule_id}", response_model=WorkflowScheduleResponse)
def update_schedule(
    schedule_id: UUID,
    payload: WorkflowScheduleUpdate,
    db: Session = Depends(get_db),
):
    schedule = db.get(WorkflowSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if payload.input is not None:
        if not schedule.definition_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This is a legacy schedule with its own step snapshot — recreate it against a workflow to give it input.",
            )
        definition = _get_definition_or_400(db, schedule.definition_id)
        schedule.input = _resolve_input_or_422(definition, payload.input)

    if payload.name is not None:
        schedule.name = payload.name
    if payload.cron_expression is not None:
        schedule.cron_expression = payload.cron_expression
        schedule.next_run_at = compute_next_run(payload.cron_expression, datetime.utcnow())
    if payload.enabled is not None:
        schedule.enabled = payload.enabled

    db.commit()
    db.refresh(schedule)
    _attach_definitions(db, [schedule])
    return schedule


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: UUID, db: Session = Depends(get_db)):
    schedule = db.get(WorkflowSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    db.delete(schedule)
    db.commit()
    return None
