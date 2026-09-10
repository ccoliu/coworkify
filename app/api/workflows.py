from app.tasks.executor import create_workflow_from_steps
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.models.task import Task
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep
from app.models.schedule import WorkflowSchedule
from app.schemas.workflow import WorkflowCreate, WorkflowResponse
from app.schemas.schedule import PromoteWorkflowToSchedule, WorkflowScheduleResponse
from app.tasks.executor import execute_task, create_workflow_from_steps
from app.core.security import get_current_user
from app.core.rate_limit import RateLimiter
from app.core.cron import compute_next_run

router = APIRouter(
    prefix='/workflows',
    tags=['Workflows'],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))]
)

def _attach_task_details(db: Session, steps: list[WorkflowStep]) -> None:
    task_ids = [s.task_id for s in steps]
    if not task_ids:
        return
    
    tasks_by_id = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(task_ids))).all()}
    for s in steps:
        task = tasks_by_id.get(s.task_id)
        if task:
            s.task_status = task.status
            s.task_name = task.name
            s.task_type = task.task_type

@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    workflow = create_workflow_from_steps(
        db, payload.name, [s.model_dump() for s in payload.steps]
    )
    _attach_task_details(db, workflow.steps)
    return workflow

@router.get("/", response_model=List[WorkflowResponse])
def list_workflows(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    stmt = select(Workflow).order_by(Workflow.created_at.desc()).offset(offset).limit(limit)
    workflows = db.scalars(stmt).all()

    all_steps = [s for w in workflows for s in w.steps]
    _attach_task_details(db, all_steps)
    return workflows
    

@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    _attach_task_details(db, workflow.steps)
    return workflow

@router.post(
    "/{workflow_id}/promote-to-schedule",
    response_model=WorkflowScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_workflow_to_schedule(
    workflow_id: UUID,
    payload: PromoteWorkflowToSchedule,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把一個已經建立過的 workflow 註冊成週期性排程，直接沿用它當初的 step 樣板。"""
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    if not workflow.steps_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This workflow has no stored step template (it was created before this feature existed) "
            "— recreate it via POST /workflows/ to enable scheduling.",
        )

    schedule = WorkflowSchedule(
        name=payload.name,
        cron_expression=payload.cron_expression,
        steps=workflow.steps_template,
        enabled=payload.enabled,
        created_by=current_user.id,
        next_run_at=compute_next_run(payload.cron_expression, datetime.utcnow()),
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule
