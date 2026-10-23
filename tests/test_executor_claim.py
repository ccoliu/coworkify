"""Exercise task ownership through real executor calls and PostgreSQL sessions."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from threading import Barrier, Event
import uuid

import pytest
from celery.exceptions import Retry
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.task import Task, TaskStatus
from app.models.task_log import TaskLog
from app.models.workflow import WorkflowStep, WorkFlowStatus
from app.tasks import executor


@pytest.fixture
def sessions(db, db_engine, monkeypatch):
    factory = sessionmaker(bind=db_engine, autoflush=False)
    monkeypatch.setattr(executor, "SessionLocal", factory)
    monkeypatch.setattr(executor, "notify_status_change", lambda *a, **kw: None)
    return factory


def make_task(db, **overrides):
    task = Task(name="claim", task_type="echo", payload={}, max_retries=0, **overrides)
    db.add(task)
    db.commit()
    return task.id


def test_concurrent_upstream_completions_execute_join_once(db, db_engine, sessions, monkeypatch):
    sent = []
    monkeypatch.setattr(executor, "dispatch_task", lambda task: sent.append(task.id))
    steps = [
        {"key": key, "name": key, "task_type": "echo", "payload": {},
         "priority": 3, "max_retries": 0, "depends_on": dependencies}
        for key, dependencies in [("a", []), ("b", []), ("join", ["a", "b"]), ("end", ["join"])]
    ]
    workflow = executor.create_workflow_from_steps(db, "fan-in", steps)
    ids = {step.step_key: step.task_id for step in db.scalars(
        select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id)
    )}
    sent.clear()
    upstreams_committed = Barrier(2)
    advance = executor.advance_workflow

    def advance_after_both_commits(session, task):
        if task.id in (ids["a"], ids["b"]):
            upstreams_committed.wait(timeout=10)
        advance(session, task)

    monkeypatch.setattr(executor, "advance_workflow", advance_after_both_commits)

    def finish_upstream(task_id):
        with sessions() as session:
            executor.record_task_success(session, session.get(Task, task_id), {})

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(finish_upstream, [ids["a"], ids["b"]]))
    # Duplicate dispatch is allowed; duplicate side effects are not.
    assert sent == [ids["join"], ids["join"]]
    sent.clear()

    both_read_pending = Barrier(2)

    class ConcurrentSession(Session):
        def get(self, entity, ident, **kwargs):
            task = super().get(entity, ident, **kwargs)
            if entity is Task and ident == ids["join"] and not self.info.get("read_join"):
                self.info["read_join"] = True
                both_read_pending.wait(timeout=10)
            return task

    monkeypatch.setattr(executor, "SessionLocal", sessionmaker(
        bind=db_engine, class_=ConcurrentSession, autoflush=False
    ))
    entered = Event()
    release = Event()
    observed_statuses = []

    def handle_join(payload):
        with sessions() as observer:
            observed_statuses.append(observer.get(Task, ids["join"]).status)
        entered.set()
        assert release.wait(timeout=15)
        return {"joined": True}

    monkeypatch.setattr(executor, "get_task_handler", lambda task_type: handle_join)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(executor.execute_task.run, str(ids["join"])) for _ in range(2)]
        try:
            assert entered.wait(timeout=10)
            done, _ = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
        finally:
            release.set()
        results = [future.result(timeout=10) for future in futures]

    assert observed_statuses == [TaskStatus.RUNNING]
    assert done, "the losing delivery must return while the owner is still executing"
    assert results.count({"joined": True}) == 1
    assert sent == [ids["end"]]
    db.expire_all()
    assert len(db.scalars(select(TaskLog).where(TaskLog.task_id == ids["join"])).all()) == 1
    monkeypatch.setattr(executor, "get_task_handler", lambda task_type: lambda payload: {"done": True})
    executor.execute_task.run(str(ids["end"]))
    db.refresh(workflow)
    assert workflow.status == WorkFlowStatus.SUCCESS
    assert workflow.result == {"end": {"done": True}}


@pytest.mark.parametrize("status", [TaskStatus.RUNNING, TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED])
def test_non_runnable_delivery_has_no_effect(db, sessions, monkeypatch, status):
    task_id = make_task(db, status=status)
    monkeypatch.setattr(executor, "get_task_handler", lambda _: pytest.fail("handler must not run"))
    executor.execute_task.run(str(task_id))
    db.expire_all()
    assert db.get(Task, task_id).status == status
    assert db.scalars(select(TaskLog)).all() == []


def test_deleted_and_missing_deliveries_have_no_effect(db, sessions, monkeypatch):
    task_id = make_task(db, deleted_at=datetime.utcnow())
    monkeypatch.setattr(executor, "get_task_handler", lambda _: pytest.fail("handler must not run"))
    assert "deleted" in executor.execute_task.run(str(task_id))
    assert "not found" in executor.execute_task.run(str(uuid.uuid4()))
    assert db.scalars(select(TaskLog)).all() == []


@pytest.mark.parametrize("change", ["cancel", "delete"])
def test_task_changed_between_read_and_claim_is_not_executed(db, db_engine, sessions, monkeypatch, change):
    task_id = make_task(db)

    class ChangedSession(Session):
        def get(self, entity, ident, **kwargs):
            task = super().get(entity, ident, **kwargs)
            if not self.info.get("changed"):
                self.info["changed"] = True
                with sessions() as other:
                    changed = other.get(Task, task_id)
                    if change == "cancel":
                        changed.status = TaskStatus.CANCELLED
                    else:
                        changed.deleted_at = datetime.utcnow()
                    other.commit()
            return task

    monkeypatch.setattr(executor, "SessionLocal", sessionmaker(bind=db_engine, class_=ChangedSession))
    monkeypatch.setattr(executor, "get_task_handler", lambda _: pytest.fail("handler must not run"))
    executor.execute_task.run(str(task_id))
    db.expire_all()
    task = db.get(Task, task_id)
    assert task.status == (TaskStatus.CANCELLED if change == "cancel" else TaskStatus.PENDING)
    assert db.scalars(select(TaskLog)).all() == []


def test_failed_claim_does_not_record_an_execution_failure(db, db_engine, sessions, monkeypatch):
    task_id = make_task(db)

    class FailedCommitSession(Session):
        def commit(self):
            raise RuntimeError("claim commit failed")

    monkeypatch.setattr(executor, "SessionLocal", sessionmaker(bind=db_engine, class_=FailedCommitSession))
    monkeypatch.setattr(executor, "get_task_handler", lambda _: pytest.fail("handler must not run"))
    monkeypatch.setattr(executor, "record_task_failure", lambda *a: pytest.fail("unclaimed task must not fail"))
    with pytest.raises(RuntimeError, match="claim commit failed"):
        executor.execute_task.run(str(task_id))
    db.expire_all()
    assert db.get(Task, task_id).status == TaskStatus.PENDING
    assert db.scalars(select(TaskLog)).all() == []


def test_handler_failure_preserves_retry_and_recovery(db, sessions, monkeypatch):
    task = Task(name="retry", task_type="echo", payload={}, max_retries=1)
    db.add(task)
    db.commit()
    task_id = task.id

    def fail(payload):
        raise ValueError("temporary failure")

    def retry(*, countdown, exc):
        assert countdown == 2
        raise Retry(exc=exc, when=countdown)

    monkeypatch.setattr(executor, "get_task_handler", lambda _: fail)
    monkeypatch.setattr(executor.execute_task, "retry", retry)
    with pytest.raises(Retry):
        executor.execute_task.run(str(task_id))
    db.refresh(task)
    assert task.status == TaskStatus.RETRYING
    assert task.retry_count == 1
    assert task.scheduled_at is not None
    monkeypatch.setattr(executor, "get_task_handler", lambda _: lambda payload: {"recovered": True})
    assert executor.execute_task.run(str(task_id)) == {"recovered": True}
    db.refresh(task)
    assert task.status == TaskStatus.SUCCESS
    assert [log.status for log in db.scalars(select(TaskLog).order_by(TaskLog.created_at))] == [
        TaskStatus.RETRYING, TaskStatus.SUCCESS
    ]


def test_handler_failure_without_retries_is_terminal(db, sessions, monkeypatch):
    task_id = make_task(db)
    monkeypatch.setattr(executor, "get_task_handler", lambda _: None)
    with pytest.raises(ValueError, match="Unknown task type"):
        executor.execute_task.run(str(task_id))
    db.expire_all()
    assert db.get(Task, task_id).status == TaskStatus.FAILED
    assert db.scalars(select(TaskLog)).one().status == TaskStatus.FAILED
