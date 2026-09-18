from app.tasks.executor import create_workflow_from_steps
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, delete, update

from app.db import get_db
from app.models.task import Task
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTemplate, WorkFlowStatus
from app.models.schedule import WorkflowSchedule
from app.schemas.workflow import WorkflowCreate, WorkflowResponse
from app.schemas.schedule import PromoteWorkflowToSchedule, WorkflowScheduleResponse
from app.tasks.executor import execute_task, create_workflow_from_steps, retry_workflow_from_failure
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
    """把這次 run 變成週期性排程：指向它所屬的定義，並沿用同一份輸入。"""
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    if not workflow.definition_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This run doesn't belong to a saved workflow — open the workflow itself to schedule it.",
        )

    schedule = WorkflowSchedule(
        name=payload.name,
        cron_expression=payload.cron_expression,
        definition_id=workflow.definition_id,
        input=workflow.input,
        enabled=payload.enabled,
        created_by=current_user.id,
        next_run_at=compute_next_run(payload.cron_expression, datetime.utcnow()),
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule

@router.post("/{workflow_id}/rerun", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def rerun_workflow(workflow_id: UUID, db: Session = Depends(get_db)):
    """
    用同一份 step 樣板再跑一次。刻意建立一個「全新的 workflow」而不是重置舊的——
    舊那次的每個 task 狀態與 task_logs 都完整保留，才查得出兩次跑的差異。
    """
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    if not workflow.steps_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This workflow has no stored step template (it was created before this feature existed) "
            "— recreate it via POST /workflows/ to enable re-running.",
        )
    
    new_workflow = create_workflow_from_steps(
        db,
        workflow.name,
        workflow.steps_template,
        definition_id=workflow.definition_id,
        definition_version=workflow.definition_version,
        run_input=workflow.input,
    )
    _attach_task_details(db, new_workflow.steps)
    return new_workflow

@router.post("/{workflow_id}/retry", response_model=WorkflowResponse)
def retry_workflow(workflow_id: UUID, db: Session = Depends(get_db)):
    """
    從失敗的步驟續跑同一個 workflow（不是建立新的）——已經成功的上游不會重跑，
    適合上游很貴的情況。整條重來請改用 /rerun。
    """
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    if workflow.status != WorkFlowStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a failed workflow can be retried — use /rerun to run it again from scratch."
        )
    
    reset_count = retry_workflow_from_failure(db, workflow)
    if reset_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This workflow is marked failed but has no failed task to retry.",
        )

    db.refresh(workflow)
    _attach_task_details(db, workflow.steps)
    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: UUID, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    task_ids = [s.task_id for s in workflow.steps]

    db.execute(delete(WorkflowStepTemplate).where(WorkflowStepTemplate.workflow_id == workflow_id))
    db.execute(delete(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id))
    # 軟刪除：Task 的列（和它的 TaskLog）留著，只是標記成已刪除。
    db.execute(
        update(Task)
        .where(Task.id.in_(task_ids), Task.deleted_at.is_(None))
        .values(deleted_at=datetime.utcnow())
    )

    db.delete(workflow)
    db.commit()
    return None