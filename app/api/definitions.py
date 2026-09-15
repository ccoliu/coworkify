from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.workflows import _attach_task_details
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.db import get_db
from app.models.user import User
from app.models.workflow import Workflow, WorkflowDefinition
from app.schemas.definition import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowRunCreate,
    resolve_run_input,
)
from app.schemas.workflow import WorkflowResponse
from app.tasks.executor import create_workflow_from_steps

router = APIRouter(
    prefix="/definitions",
    tags=["Workflow definitions"],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))]
)

def _get_definition_or_404(db: Session, definitions_id: UUID) -> WorkflowDefinition:
    definition = db.get(WorkflowDefinition, definitions_id)
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow definition not found"
        )
    return definition

def _attach_run_stats(db: Session, definitions: list[WorkflowDefinition]) -> None:
    """掛上 run_count 與 last_run，兩條查詢搞定整頁，不逐筆查。"""
    ids = [d.id for d in definitions]
    if not ids:
        return

    counts = dict(
        db.execute(
            select(Workflow.definition_id, func.count())
            .where(Workflow.definition_id.in_(ids))
            .group_by(Workflow.definition_id)
        ).all()
    )
    # PostgreSQL DISTINCT ON：每個 definition 只取最新一筆 run
    latest = db.scalars(
        select(Workflow)
        .where(Workflow.definition_id.in_(ids))
        .distinct(Workflow.definition_id)
        .order_by(Workflow.definition_id, Workflow.created_at.desc())
    ).all()

    latest_by_def = {w.definition_id: w for w in latest}

    for d in definitions:
        d.run_count = counts.get(d.id, 0)
        d.last_run = latest_by_def.get(d.id)

@router.post("/", response_model=WorkflowDefinitionResponse, status_code=status.HTTP_201_CREATED)
def create_definition(
    payload: WorkflowDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    definition = WorkflowDefinition(
        name = payload.name,
        description = payload.description,
        steps = [s.model_dump() for s in payload.steps],
        input_schema = [f.model_dump() for f in payload.input_schema],
        created_by = current_user.id
    )
    db.add(definition)
    db.commit()
    db.refresh(definition)
    return definition

@router.get("/", response_model=List[WorkflowDefinitionResponse])
def list_definitions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    definitions = db.scalars(
        select(WorkflowDefinition)
        .order_by(WorkflowDefinition.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    _attach_run_stats(db, definitions)
    return definitions 

@router.get("/{definition_id}", response_model=WorkflowDefinitionResponse)
def get_definition(definition_id: UUID, db: Session = Depends(get_db)):
    definition = _get_definition_or_404(db, definition_id)
    _attach_run_stats(db, [definition])
    return definition

@router.put("/{definition_id}", response_model=WorkflowDefinitionResponse)
def replace_definition(
    definition_id: UUID,
    payload: WorkflowDefinitionCreate,
    db: Session = Depends(get_db),
):
    """整份取代。已經跑過的 run 各自留有 steps_template 快照，不受影響。"""
    definition = _get_definition_or_404(db, definition_id)
    
    new_steps = [s.model_dump() for s in payload.steps]
    new_schema = [f.model_dump() for f in payload.input_schema]
    if new_steps != definition.steps or new_schema != definition.input_schema:
        definition.version += 1

    definition.name = payload.name
    definition.description = payload.description
    definition.steps = new_steps
    definition.input_schema = new_schema
    db.commit()
    db.refresh(definition)
    _attach_run_stats(db, [definition])
    return definition

@router.post("/{definition_id}/runs", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def run_definition(
    definition_id: UUID,
    payload: WorkflowRunCreate,
    db: Session = Depends(get_db),
):
    definition = _get_definition_or_404(db, definition_id)

    if definition.input_schema:
        try:
            run_input = resolve_run_input(definition.input_schema, payload.input)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    elif payload.input:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail="This definition declares no input_schema, so a run takes no input."
        )
    else:
        # 沒有 input_schema：不注入，input step（若有）維持定義裡寫死的 data
        run_input = None
    
    workflow = create_workflow_from_steps(
        db,
        definition.name,
        definition.steps,
        definition_id=definition.id,
        definition_version=definition.version,
        run_input=run_input,
    )
    _attach_task_details(db, workflow.steps)
    return workflow

@router.get("/{definition_id}/runs", response_model=List[WorkflowResponse])
def list_definition_runs(
    definition_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _get_definition_or_404(db, definition_id)
    runs = db.scalars(
        select(Workflow)
        .where(Workflow.definition_id == definition_id)
        .order_by(Workflow.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    _attach_task_details(db, [s for w in runs for s in w.steps])
    return runs
