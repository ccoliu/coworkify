"""
觸發器共用的「建 run」，以及 workflow 觸發器：一條 run 結束時，啟動等著它的下游產線。

advance_workflow 把 run 標成 SUCCESS / FAILED 後，若有觸發器在等這條產線，就派一個
coworkify.fire_workflow_triggers；下游的輸入有問題、建立失敗，都只記在觸發器上，
不會回頭影響已經結束的上游 run。
"""
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.celery_app import celery_app
from app.core.webhooks import extract_input, matches_filter
from app.db import SessionLocal
from app.models.trigger import TriggerKind, WorkflowTrigger
from app.models.workflow import Workflow, WorkflowDefinition
from app.schemas.definition import resolve_run_input
from app.tasks.executor import create_workflow_from_steps
from app.tasks.subworkflow import SUBWORKFLOW, parent_run

logger = logging.getLogger(__name__)

# 觸發鏈最多幾層。建立觸發器時已經擋掉循環，這是第二道保險：
# 兩個請求同時建出互相指向的觸發器時，循環檢查可能各自都通過。
MAX_CHAIN_DEPTH = 10


def find_delivered_run(db, trigger_id, delivery_id: str) -> Workflow | None:
    return db.scalars(
        select(Workflow).where(Workflow.trigger_id == trigger_id, Workflow.trigger_delivery_id == delivery_id)
    ).first()


def record_trigger_error(db, trigger: WorkflowTrigger, message: str) -> None:
    trigger.last_error = message
    trigger.last_error_at = datetime.utcnow()
    db.commit()


def start_triggered_run(db, trigger: WorkflowTrigger, document: dict, delivery_id: str | None) -> tuple[Workflow, bool]:
    """
    依觸發器的 input_mapping 從 document 取出輸入，建一個 run。
    回傳 (run, 是否新建立)；同一個 delivery_id 之前建過就回傳那一個、不再建。
    輸入不合定義的 input_schema、或定義本身有問題時丟 ValueError，由呼叫端決定怎麼回報。
    """
    if delivery_id:
        existing = find_delivered_run(db, trigger.id, delivery_id)
        if existing:
            return existing, False

    definition = db.get(WorkflowDefinition, trigger.definition_id)
    run_input = (
        resolve_run_input(definition.input_schema, extract_input(document, trigger.input_mapping or {}))
        if definition.input_schema
        else None
    )

    try:
        workflow = create_workflow_from_steps(
            db,
            definition.name,
            definition.steps,
            definition_id=definition.id,
            definition_version=definition.version,
            run_input=run_input,
            created_by=trigger.created_by,
            trigger_kind=trigger.kind,
            trigger_id=trigger.id,
            trigger_delivery_id=delivery_id,
        )
    except IntegrityError:
        # 同一個 delivery 同時來了兩次，都通過了上面的檢查；unique constraint 擋下後到的那次
        db.rollback()
        existing = find_delivered_run(db, trigger.id, delivery_id) if delivery_id else None
        if existing is None:
            raise
        return existing, False
    except ValueError:
        db.rollback()
        raise
    

    trigger.last_triggered_at = datetime.utcnow()
    trigger.last_error = None
    trigger.last_error_at = None
    db.commit()
    return workflow, True


def upstream_run_id(run: Workflow) -> uuid.UUID | None:
    """workflow 觸發器啟動的 run，是哪一個上游 run 結束時啟動的；其他 run 回傳 None。"""
    if run.trigger_kind != TriggerKind.WORKFLOW or not run.trigger_delivery_id:
        return None
    # delivery id 是 "<上游 run id>:<狀態>"
    try:
        return uuid.UUID(run.trigger_delivery_id.split(":", 1)[0])
    except ValueError:
        return None

def upstream_outcome(run: Workflow) -> str | None:
    """上游 run 以什麼結果結束才啟動了這個 run："success" / "failed"；不是 workflow 觸發器啟動的回傳 None。"""
    if upstream_run_id(run) is None:
        return None
    return run.trigger_delivery_id.split(":", 1)[1] if ":" in run.trigger_delivery_id else None 


def downstream_runs(db, run: Workflow) -> list[Workflow]:
    """這個 run 結束時，workflow 觸發器啟動了哪些 run（舊的在前）。"""
    return db.scalars(
        select(Workflow)
        .where(
            Workflow.trigger_kind == TriggerKind.WORKFLOW,
            # 用等號而不是 LIKE '<id>:%'，才吃得到 trigger_delivery_id 的 index
            Workflow.trigger_delivery_id.in_([f"{run.id}:success", f"{run.id}:failed"]),
        )
        .order_by(Workflow.created_at)
    ).all()


def _chain_depth(db, run: Workflow) -> int:
    """這個 run 是經過幾層 workflow 觸發器才啟動的（手動、排程、webhook 啟動的是 0）。"""
    depth = 0
    current = run
    while current is not None and depth < MAX_CHAIN_DEPTH:
        parent_id = upstream_run_id(current)
        if parent_id is not None:
            current = db.get(Workflow, parent_id)
        elif current.trigger_kind == SUBWORKFLOW:
            # 子 run 也算一層：A 呼叫 B、B 結束又觸發 A，這種圈只能靠深度上限擋下
            current = parent_run(db, current)
        else:
            break
        depth += 1
    return depth


def run_workflow_triggers(db, source_id: uuid.UUID, status: str) -> int:
    """source 這個 run 以 status 結束了，啟動所有等著它的觸發器。回傳新建立的 run 數。"""
    source = db.get(Workflow, source_id)
    if source is None or source.definition_id is None:
        return 0

    
    triggers = db.scalars(
        select(WorkflowTrigger).where(
            WorkflowTrigger.kind == TriggerKind.WORKFLOW,
            WorkflowTrigger.enabled == True,
            WorkflowTrigger.source_definition_id == source.definition_id,
            WorkflowTrigger.on_status.in_([status, "any"]),
            # 只接自己的 run：觸發器的擁有者必須也是上游 run 的擁有者
            WorkflowTrigger.created_by == source.created_by,
        )
    ).all()
    if not triggers:
        return 0

    document = {
        "workflow_id": str(source.id),
        "status": status,
        "result": source.result or {},
        "input": source.input or {},
    }
    # 同一個上游 run、同一種結束狀態只觸發一次。retry 後成功會再觸發 success 那一邊；
    # retry 後又失敗不會再觸發一次 failed。
    delivery_id = f"{source.id}:{status}"
    depth = _chain_depth(db, source)

    started = 0
    for trigger in triggers:
        if depth >= MAX_CHAIN_DEPTH:
            record_trigger_error(db, trigger, f"ChainTooDeep: already {depth} workflow triggers deep, not starting another run")
            continue
        if not matches_filter(document, trigger.filter or {}):
            continue
        try:
            _, created = start_triggered_run(db, trigger, document, delivery_id)
        except Exception as exc:
            db.rollback()
            logger.exception("Workflow trigger %s (%s) failed to start a run", trigger.name, trigger.id)
            record_trigger_error(db, trigger, f"{type(exc).__name__}: {exc}")
            continue
        started += int(created)
    return started


@celery_app.task(name="coworkify.fire_workflow_triggers")
def fire_workflow_triggers(source_id: str, status: str):
    db = SessionLocal()
    try:
        return run_workflow_triggers(db, uuid.UUID(source_id), status)
    finally:
        db.close()