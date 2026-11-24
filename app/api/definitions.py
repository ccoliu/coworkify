from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.workflows import _attach_task_details
from app.core.ownership import get_owned_or_404
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
from app.tasks.subworkflow import SUBWORKFLOW, calls_back_into, child_input

router = APIRouter(
    prefix="/definitions",
    tags=["Workflow definitions"],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))]
)

def _get_definition_or_404(db: Session, definition_id: UUID, user: User) -> WorkflowDefinition:
    return get_owned_or_404(db, WorkflowDefinition, definition_id, user, "Workflow definition not found")

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

def _check_subworkflows_or_400(db: Session, user: User, steps: list[dict], self_id: UUID | None = None) -> None:
    """
    subworkflow 步驟要呼叫的定義必須存在、是自己的、輸入欄位都有宣告，而且不能繞回這份定義本身。
    在存檔時擋，不是等跑到那一步才失敗。新建的定義還沒有 id，別人不可能呼叫它，不會成環。
    """
    for step in steps:
        if step["task_type"] != SUBWORKFLOW:
            continue
        key = step["key"]
        try:
            child_id = UUID(str(step["payload"].get("definition_id")))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Step '{key}' subworkflow definition_id must be a valid UUID"
            )
        child = db.get(WorkflowDefinition, child_id)
        if child is None or child.created_by != user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Step '{key}' subworkflow definition not found or not owned by you."
            )
        if self_id is not None and calls_back_into(db, {child_id}, self_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Step '{key}': '{child.name}' leads back to this workflow, which would loop forever"
            )
        declared = {f["key"] for f in child.input_schema or []}
        unknown = sorted(set(child_input(step["payload"])) - declared)
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Step '{key}' passes {', '.join(unknown)}, which '{child.name}' doesn't take as input",
            )



@router.post("/", response_model=WorkflowDefinitionResponse, status_code=status.HTTP_201_CREATED)
def create_definition(
    payload: WorkflowDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    steps = [s.model_dump() for s in payload.steps]
    _check_subworkflows_or_400(db, current_user, steps)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    definitions = db.scalars(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.created_by == current_user.id)
        .order_by(WorkflowDefinition.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    _attach_run_stats(db, definitions)
    return definitions 

@router.get("/{definition_id}", response_model=WorkflowDefinitionResponse)
def get_definition(
    definition_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    definition = _get_definition_or_404(db, definition_id, current_user)
    _attach_run_stats(db, [definition])
    return definition

@router.put("/{definition_id}", response_model=WorkflowDefinitionResponse)
def replace_definition(
    definition_id: UUID,
    payload: WorkflowDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """整份取代。已經跑過的 run 各自留有 steps_template 快照，不受影響。"""
    definition = _get_definition_or_404(db, definition_id, current_user)
    
    new_steps = [s.model_dump() for s in payload.steps]
    _check_subworkflows_or_400(db, current_user, new_steps, self_id=definition_id)
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
    current_user: User = Depends(get_current_user),
):
    definition = _get_definition_or_404(db, definition_id, current_user)

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
        created_by=current_user.id,
    )
    _attach_task_details(db, workflow.steps)
    return workflow

@router.get("/{definition_id}/runs", response_model=List[WorkflowResponse])
def list_definition_runs(
    definition_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_definition_or_404(db, definition_id, current_user)
    runs = db.scalars(
        select(Workflow)
        .where(Workflow.definition_id == definition_id, Workflow.created_by == current_user.id)
        .order_by(Workflow.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    _attach_task_details(db, [s for w in runs for s in w.steps])
    return runs
