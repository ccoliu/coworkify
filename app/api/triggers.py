from collections import defaultdict
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.connection_crypto import ConnectionsKeyMissing, encrypt
from app.core.ownership import get_owned_or_404
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.core.webhooks import new_secret
from app.db import get_db
from app.models.trigger import TriggerKind, WorkflowTrigger
from app.models.user import User
from app.models.workflow import WorkflowDefinition
from app.schemas.trigger import (
    WorkflowTriggerCreate,
    WorkflowTriggerResponse,
    WorkflowTriggerUpdate,
    WorkflowTriggerWithSecret,
)

router = APIRouter(
    prefix="/triggers",
    tags=["Triggers"],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))],
)


def _get_trigger_or_404(db: Session, trigger_id: UUID, user: User) -> WorkflowTrigger:
    return get_owned_or_404(db, WorkflowTrigger, trigger_id, user, "Trigger not found")


def _get_definition_or_400(db: Session, definition_id: UUID, user: User) -> WorkflowDefinition:
    definition = db.get(WorkflowDefinition, definition_id)
    if not definition or definition.created_by != user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow definition not found")
    return definition


def _check_mapping_or_400(definition: WorkflowDefinition, mapping: dict) -> None:
    """mapping 的鍵必須是定義宣告過的輸入欄位，打錯字要在存檔時發現，不是等觸發時才失敗。"""
    declared = {f["key"] for f in definition.input_schema or []}
    unknown = sorted(set(mapping) - declared)
    if unknown:
        hint = "This definition declares no input_schema." if not declared else f"Declared fields: {', '.join(sorted(declared))}."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"input_mapping uses undeclared input fields: {', '.join(unknown)}. {hint}",
        )


def _would_loop(db: Session, user: User, source_id: UUID, target_id: UUID) -> bool:
    """
    加上「source 結束 → 啟動 target」這條邊之後，會不會出現循環：
    target 沿著既有的 workflow 觸發器能走回 source，就會。停用的觸發器也算——
    之後重新啟用時不會再檢查一次。
    """
    if source_id == target_id:
        return True
    edges = db.execute(
        select(WorkflowTrigger.source_definition_id, WorkflowTrigger.definition_id).where(
            WorkflowTrigger.kind == TriggerKind.WORKFLOW, WorkflowTrigger.created_by == user.id
        )
    ).all()
    downstream = defaultdict(set)
    for source, target in edges:
        downstream[source].add(target)

    stack, seen = [target_id], set()
    while stack:
        node = stack.pop()
        if node == source_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(downstream[node])
    return False


def _encrypt_or_503(value: str) -> str:
    try:
        return encrypt(value)
    except ConnectionsKeyMissing as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


def _with_hook_path(trigger: WorkflowTrigger) -> WorkflowTrigger:
    trigger.hook_path = f"/hooks/{trigger.id}" if trigger.kind == TriggerKind.WEBHOOK else None
    return trigger


@router.post("/", response_model=WorkflowTriggerWithSecret, status_code=status.HTTP_201_CREATED)
def create_trigger(
    payload: WorkflowTriggerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    definition = _get_definition_or_400(db, payload.definition_id, current_user)
    _check_mapping_or_400(definition, payload.input_mapping)

    secret = None
    if payload.kind == TriggerKind.WORKFLOW:
        source = _get_definition_or_400(db, payload.source_definition_id, current_user)
        if _would_loop(db, current_user, source.id, definition.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This would make a loop: '{definition.name}' already leads back to '{source.name}' "
                "(or they are the same workflow).",
            )
    else:
        secret = new_secret()

    trigger = WorkflowTrigger(
        name=payload.name,
        kind=payload.kind,
        definition_id=definition.id,
        encrypted_secret=_encrypt_or_503(secret) if secret else None,
        source_definition_id=payload.source_definition_id,
        on_status=payload.on_status if payload.kind == TriggerKind.WORKFLOW else None,
        input_mapping=payload.input_mapping,
        filter=payload.filter,
        enabled=payload.enabled,
        created_by=current_user.id,
    )
    db.add(trigger)
    db.commit()
    db.refresh(trigger)
    _with_hook_path(trigger)
    trigger.secret = secret
    return trigger


@router.get("/", response_model=List[WorkflowTriggerResponse])
def list_triggers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    triggers = db.scalars(
        select(WorkflowTrigger)
        .where(WorkflowTrigger.created_by == current_user.id)
        .order_by(WorkflowTrigger.created_at.desc())
    ).all()
    return [_with_hook_path(t) for t in triggers]


@router.get("/{trigger_id}", response_model=WorkflowTriggerResponse)
def get_trigger(trigger_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _with_hook_path(_get_trigger_or_404(db, trigger_id, current_user))


@router.patch("/{trigger_id}", response_model=WorkflowTriggerResponse)
def update_trigger(
    trigger_id: UUID,
    payload: WorkflowTriggerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trigger = _get_trigger_or_404(db, trigger_id, current_user)
    if payload.input_mapping is not None:
        definition = _get_definition_or_400(db, trigger.definition_id, current_user)
        _check_mapping_or_400(definition, payload.input_mapping)
        trigger.input_mapping = payload.input_mapping
    if payload.on_status is not None:
        if trigger.kind != TriggerKind.WORKFLOW:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="on_status only applies to workflow triggers")
        trigger.on_status = payload.on_status
    if payload.filter is not None:
        trigger.filter = payload.filter
    if payload.name is not None:
        trigger.name = payload.name
    if payload.enabled is not None:
        trigger.enabled = payload.enabled
    db.commit()
    db.refresh(trigger)
    return _with_hook_path(trigger)


@router.post("/{trigger_id}/rotate-secret", response_model=WorkflowTriggerWithSecret)
def rotate_secret(trigger_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """secret 外流時換一組；舊的立刻失效，外部系統要跟著更新。"""
    trigger = _get_trigger_or_404(db, trigger_id, current_user)
    if trigger.kind != TriggerKind.WEBHOOK:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only webhook triggers have a secret")
    secret = new_secret()
    trigger.encrypted_secret = _encrypt_or_503(secret)
    db.commit()
    db.refresh(trigger)
    _with_hook_path(trigger)
    trigger.secret = secret
    return trigger


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trigger(trigger_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.delete(_get_trigger_or_404(db, trigger_id, current_user))
    db.commit()
    return None
