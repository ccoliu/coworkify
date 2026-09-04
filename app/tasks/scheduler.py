from datetime import datetime
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models.schedule import WorkflowSchedule
from app.tasks.executor import create_workflow_from_steps
from app.core.cron import compute_next_run

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
            run_name = f"{sched.name} @ {now.strftime('%Y-%m-%d %H:%M:%S')}"
            create_workflow_from_steps(db, run_name, sched.steps)
            sched.last_run_at = now
            sched.next_run_at = compute_next_run(sched.cron_expression, now)
            db.add(sched)
        db.commit()
    finally:
        db.close()