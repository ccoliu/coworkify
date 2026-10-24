# ---------------------------------------------------
# Coworkify — cron schedule triggering (issue #5)
#
# run_due_schedules is what the Beat job calls every minute. A trigger that
# fails (most often: the definition's input_schema changed and the
# schedule's saved input no longer validates) must stay visible on the
# schedule as last_error, must not move last_run_at — that field means "a
# run was actually created" — and must not stop the other due schedules.
# ---------------------------------------------------

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.schedule import WorkflowSchedule
from app.models.workflow import Workflow, WorkflowDefinition
from app.tasks import executor
from app.tasks.scheduler import run_due_schedules

NOW = datetime(2026, 10, 25, 4, 5, 0)
STEPS = [{"key": "input_1", "name": "input", "task_type": "input", "payload": {}, "priority": 3}]
SCHEMA = [{"key": "repo", "label": "Repository", "kind": "string", "required": True}]


@pytest.fixture(autouse=True)
def no_dispatch(monkeypatch):
    monkeypatch.setattr(executor, "dispatch_task", lambda task, countdown=None: None)


def make_schedule(db, *, input, next_run_at=NOW - timedelta(minutes=1), enabled=True, **extra) -> WorkflowSchedule:
    definition = WorkflowDefinition(name="pipeline", steps=STEPS, input_schema=SCHEMA)
    db.add(definition)
    db.flush()
    sched = WorkflowSchedule(
        name="hourly", cron_expression="5 * * * *", definition_id=definition.id,
        input=input, steps=[], enabled=enabled, next_run_at=next_run_at, **extra,
    )
    db.add(sched)
    db.commit()
    return sched


def runs_of(db, sched) -> list[Workflow]:
    return db.scalars(select(Workflow).where(Workflow.definition_id == sched.definition_id)).all()


def reload(db, sched) -> WorkflowSchedule:
    db.expire_all()
    return db.get(WorkflowSchedule, sched.id)


def test_a_due_schedule_creates_a_run_and_records_it(db):
    sched = make_schedule(db, input={"repo": "apache/airflow"})

    assert run_due_schedules(db, NOW) == 1

    done = reload(db, sched)
    assert done.last_run_at == NOW
    assert done.last_error is None
    assert done.next_run_at > NOW
    (run,) = runs_of(db, sched)
    assert run.input == {"repo": "apache/airflow"}


def test_a_failed_trigger_is_recorded_without_pretending_it_ran(db):
    before = NOW - timedelta(hours=1)
    sched = make_schedule(db, input={}, last_run_at=before)  # repo 是必填，卻沒有填

    assert run_due_schedules(db, NOW) == 0

    failed = reload(db, sched)
    assert failed.last_run_at == before
    assert failed.last_error_at == NOW
    assert "Repository" in failed.last_error
    # 時間照常往前推，不會每分鐘重試同一個壞掉的排程
    assert failed.next_run_at > NOW
    assert runs_of(db, sched) == []


def test_one_broken_schedule_does_not_stop_the_others(db):
    broken = make_schedule(db, input={})
    healthy = make_schedule(db, input={"repo": "x"})

    assert run_due_schedules(db, NOW) == 1

    assert reload(db, broken).last_error is not None
    assert reload(db, healthy).last_run_at == NOW
    assert len(runs_of(db, healthy)) == 1


def test_a_later_success_clears_the_previous_error(db):
    sched = make_schedule(db, input={})
    run_due_schedules(db, NOW)

    fixed = reload(db, sched)
    fixed.input = {"repo": "x"}
    fixed.next_run_at = NOW
    db.commit()
    later = NOW + timedelta(hours=1)
    run_due_schedules(db, later)

    ok = reload(db, sched)
    assert ok.last_run_at == later
    assert ok.last_error is None
    assert ok.last_error_at is None


def test_schedules_that_are_not_due_or_disabled_are_left_alone(db):
    future = make_schedule(db, input={"repo": "x"}, next_run_at=NOW + timedelta(minutes=5))
    disabled = make_schedule(db, input={"repo": "x"}, enabled=False)

    assert run_due_schedules(db, NOW) == 0
    assert runs_of(db, future) == []
    assert runs_of(db, disabled) == []
