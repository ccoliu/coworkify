# ---------------------------------------------------
# Coworkify — task claiming and stale-RUNNING recovery (issues #1 and #3)
#
# execute_task claims a task with one conditional UPDATE before running its
# handler, so a task delivered twice (two upstreams finishing at once, a
# broker redelivery) runs once. recover_stale_running_tasks covers the other
# side: a worker that dies after claiming leaves the task in RUNNING, and the
# Beat job turns that into an ordinary failure — retried while retries
# remain, FAILED with downstream cancelled once they run out.
#
# execute_task is called directly (in-process, no broker), with SessionLocal
# pointed at the test database. Handlers are replaced; max_retries is 0
# wherever a handler fails, because a directly-called Celery task re-raises
# instead of scheduling self.retry.
# ---------------------------------------------------

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.task import Task, TaskStatus
from app.models.task_log import TaskLog
from app.models.workflow import Workflow, WorkflowStep, WorkFlowStatus
from app.tasks import executor
from app.tasks.executor import (
    create_workflow_from_steps,
    execute_task,
    recover_stale_running_tasks,
)

NOW = datetime(2026, 10, 24, 12, 0, 0)

@pytest.fixture
def worker_db(db_engine, monkeypatch):
    """execute_task 自己開 session；讓它開到測試資料庫。"""
    monkeypatch.setattr(executor, "SessionLocal", sessionmaker(bind=db_engine, autoflush=False))

@pytest.fixture
def dispatched(monkeypatch):
    sent: list = []
    monkeypatch.setattr(
        executor, "dispatch_task", lambda task, countdown=None: sent.append((task.id, countdown))
    )
    monkeypatch.setattr(executor, "notify_status_change", lambda *a, **kw: None)
    return sent

def use_handler(monkeypatch, handler):
    monkeypatch.setattr(executor, "get_task_handler", lambda task_type: handler)

def make_task(db, *, status=TaskStatus.PENDING, task_type="echo", max_retries=0, **extra) -> Task:
    task = Task(
        name="t",
        task_type=task_type,
        payload={},
        max_retries=max_retries,
        status=status,
        created_at=NOW,
        priority=3,
        **extra,
    )
    db.add(task)
    db.commit()
    return task

def logs_of(db, task) -> list[str]:
    rows = db.scalars(
        select(TaskLog).where(TaskLog.task_id == task.id).order_by(TaskLog.created_at)
    ).all()
    return [row.status for row in rows]

def reload(db, task) -> Task:
    db.expire_all()
    return db.get(Task, task.id)

# --- 認領 -------------------------------------------------------------------

def test_a_stale_running_task_is_retried_and_can_run_again(db, worker_db, dispatched, monkeypatch):
    task = make_task(db,status=TaskStatus.RUNNING, max_retries=3, claimed_at=NOW - timedelta(minutes=11))

    assert recover_stale_running_tasks(db, NOW) == 1

    retried = reload(db, task)
    assert retried.status == TaskStatus.RETRYING
    assert retried.retry_count == 1
    assert retried.claimed_at is None
    assert dispatched == [(task.id, 2)]

    # 重新派送的那次投遞拿得到執行權
    use_handler(monkeypatch, lambda payload: {"ok": True})
    execute_task(str(task.id))
    assert reload(db, task).status == TaskStatus.SUCCESS

def test_recently_claimed_tasks_are_left_running(db, dispatched):
    fresh = make_task(db, status=TaskStatus.RUNNING, max_retries=3, claimed_at = NOW - timedelta(minutes=9))
    # agent_step 的上限比較長：20 分鐘還算正常
    agent = make_task(
        db, status=TaskStatus.RUNNING, task_type="agent_step", max_retries=3,
        claimed_at = NOW - timedelta(minutes=20),
    )

    assert recover_stale_running_tasks(db, NOW) == 0
    assert reload(db, fresh).status == TaskStatus.RUNNING
    assert reload(db, agent).status == TaskStatus.RUNNING
    assert dispatched == []

def test_a_stale_task_with_no_retries_left_fails_and_cancels_downstream(db, dispatched):
    steps = [
        {"key": "a", "name": "a", "task_type": "echo", "payload": {}, "priority": 3, "max_retries": 0},
        {"key": "b", "name": "b", "task_type": "echo", "payload": {}, "priority": 3, "depends_on": ["a"]},
    ]

    workflow = create_workflow_from_steps(db, "wf", steps)
    a, b = (
        db.get(Task, db.scalars(
            select(WorkflowStep.task_id).where(
                WorkflowStep.workflow_id == workflow.id,
                WorkflowStep.step_key == key
            )
        ).one())
        for key in ("a", "b")
    )
    a.status = TaskStatus.RUNNING
    a.claimed_at = NOW - timedelta(hours=1)
    db.commit()
    dispatched.clear()

    assert recover_stale_running_tasks(db, NOW) == 1
    
    assert reload(db, a).status == TaskStatus.FAILED
    assert reload(db, b).status == TaskStatus.CANCELLED
    assert db.get(Workflow, workflow.id).status == WorkFlowStatus.FAILED
    assert dispatched == []

def test_a_late_result_from_the_lost_worker_is_not_run_twice(db, worker_db, dispatched, monkeypatch):
    # 回收之後，原本那個 worker 其實還活著、把結果寫回來了：重新派送的投遞就不該再執行
    task = make_task(db, status=TaskStatus.RUNNING, max_retries=3, claimed_at=NOW - timedelta(minutes=11))
    recover_stale_running_tasks(db, NOW)

    late = reload(db, task)
    late.status = TaskStatus.RUNNING
    executor.record_task_success(db, late, {"ok": True})

    use_handler(monkeypatch, lambda payload: pytest.fail("handler must not run"))
    execute_task(str(task.id))
    assert reload(db, task).status == TaskStatus.SUCCESS