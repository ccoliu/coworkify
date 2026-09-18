from datetime import datetime
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models.schedule import WorkflowSchedule
from app.models.workflow import WorkflowDefinition
from app.schemas.definition import resolve_run_input
from app.tasks.executor import create_workflow_from_steps
from app.core.cron import compute_next_run

def _trigger(db, sched: WorkflowSchedule, now: datetime) -> None:
    if not sched.definition_id:
        # 舊排程：自己帶著一份 step 快照，沒有定義可以指
        create_workflow_from_steps(db, f"{sched.name} @ {now.strftime('%Y-%m-%d %H:%M:%S')}", sched.steps or [])
        return
    
    definition = db.get(WorkflowDefinition, sched.definition_id)
    if not definition:
        # FK 是 ON DELETE CASCADE，理論上排程會先消失，這裡只是保險
        return
    
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
    )

@celery_app.task(name="coworkify.check_due_schedules")
def check_due_schedules():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due = db.scalars(
            select(WorkflowSchedule).where(
                WorkflowSchedule.enabled == True,
                WorkflowSchedule.next_run_at <= now
            )
        ).all()

        for sched in due:
            try:
                _trigger(db, sched, now)
            except Exception as exc:
                # 定義改過、input 不再合法時，只跳過這一個排程，不要害整批都不動。
                # 時間照常往前推，否則每 5 秒就會重試一次同一個壞掉的排程。
                db.rollback()
                print(f"Schedule {sched.name} failed: {exc}")
            
            sched.last_run_at = now
            sched.next_run_at = compute_next_run(sched.cron_expression, now)
            db.add(sched)
            db.commit()
    finally:
        db.close()