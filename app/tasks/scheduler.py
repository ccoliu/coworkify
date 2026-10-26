import logging
from datetime import datetime
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models.schedule import WorkflowSchedule
from app.models.workflow import WorkflowDefinition
from app.schemas.definition import resolve_run_input
from app.tasks.executor import create_workflow_from_steps
from app.core.cron import compute_next_run

logger = logging.getLogger(__name__)

def _trigger(db, sched: WorkflowSchedule, now: datetime) -> None:
    if not sched.definition_id:
        # 舊排程：自己帶著一份 step 快照，沒有定義可以指
        create_workflow_from_steps(
            db, f"{sched.name} @ {now.strftime('%Y-%m-%d %H:%M:%S')}", sched.steps or [],
            created_by=sched.created_by,
        )
        return
    
    definition = db.get(WorkflowDefinition, sched.definition_id)
    if not definition:
        # FK 是 ON DELETE CASCADE，理論上排程會先消失；真的發生就當成一次失敗記下來，
        # 不要靜悄悄地什麼都沒建立
        raise LookupError(f"workflow definition {sched.definition_id} no longer exists")
    
    run_input = (
        resolve_run_input(definition.input_schema, sched.input or {})
        if definition.input_schema is not None
        else None
    )
    create_workflow_from_steps(
        db,
        definition.name,
        definition.steps,
        definition_id=definition.id,
        definition_version=definition.version,
        run_input=run_input,
        created_by=sched.created_by,
    )

@celery_app.task(name="coworkify.check_due_schedules")
def check_due_schedules():
    db = SessionLocal()
    try:
        return run_due_schedules(db, datetime.utcnow())
    finally:
        db.close()

def run_due_schedules(db, now:datetime) -> int:
    """觸發所有到期的排程，回傳成功建立 run 的數量。"""
    due = db.scalars(
        select(WorkflowSchedule).where(
            WorkflowSchedule.enabled == True,
            WorkflowSchedule.next_run_at <= now
        )
    ).all()

    triggered = 0
    for sched in due:
        try:
            _trigger(db, sched, now)
        except Exception as exc:
            # 定義改過、input 不再合法時，只跳過這一個排程，不要害整批都不動。
            # 失敗要留在排程上讓 UI 看得到；last_run_at 不動，它只代表「真的建立了 run」。
            db.rollback()
            logger.exception("Schedule %s (%s) failed to trigger", sched.name, sched.id)
            sched.last_error = f"{type(exc).__name__}: {exc}"
            sched.last_error_at = now
        else:
            sched.last_error = None
            sched.last_error_at = None
            sched.last_run_at = now
            triggered += 1

        # 成功或失敗，時間都照常往前推，否則每分鐘都會重試一次同一個壞掉的排程
        sched.next_run_at = compute_next_run(sched.cron_expression, now)
        db.add(sched)
        db.commit()
    return triggered