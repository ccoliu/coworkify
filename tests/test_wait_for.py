# ---------------------------------------------------
# Coworkify — wait_for sensor (reschedule mode)
#
# A sensor checks an outside condition and gives the worker back between
# checks: NotReady moves the task to WAITING and schedules the next check.
# What has to hold:
#   - waiting is not failing: it costs no retries and writes one log row;
#   - a timeout fails the task for good and cancels downstream;
#   - an early or duplicate message can't start a second polling chain;
#   - a delayed message lost with its worker is sent again.
#
# execute_task is called directly with SessionLocal pointed at the test
# database. Nothing connects out: requests is replaced and IP literals
# resolve without a DNS lookup.
# ---------------------------------------------------

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.task import Task, TaskStatus
from app.models.task_log import TaskLog
from app.models.workflow import Workflow, WorkflowStep, WorkFlowStatus
from app.tasks import executor, handler
from app.tasks.connections import misplaced_connection_refs
from app.tasks.executor import (
    create_workflow_from_steps,
    execute_task,
    recover_lost_waiting_tasks,
    recover_stale_running_tasks,
    retry_workflow_from_failure,
)
from app.tasks.handler import NotReady, handle_wait_for

URL = "https://93.184.216.34/runs"
NOW = datetime(2026, 11, 8, 12, 0, 0)


class FakeResponse:
    def __init__(self, status=200, json_body=None, text=""):
        self.status_code = status
        self._json = json_body
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


@pytest.fixture
def respond(monkeypatch):
    """讓 requests.get 回傳指定內容，並記下呼叫參數。"""
    calls: list = []

    def set_response(response):
        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return response

        monkeypatch.setattr(handler.requests, "get", fake_get)
        return calls

    return set_response


def payload(**overrides):
    return {"url": URL, "path": "status", "expected": "done", **overrides}


# --- handler ----------------------------------------------------------------


def test_returns_the_response_when_the_condition_holds(respond):
    body = {"status": "done", "id": 7}
    calls = respond(FakeResponse(json_body=body))

    result = handle_wait_for({**payload(), "_sensor": {"waited_seconds": 42.9}})

    assert result == {"status_code": 200, "response_body": body, "waited_seconds": 42}
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["timeout"] == 10


def test_not_ready_carries_the_interval(respond):
    respond(FakeResponse(json_body={"status": "running"}))

    with pytest.raises(NotReady) as raised:
        handle_wait_for(payload(interval_seconds=45))

    assert raised.value.poke_after == 45
    assert "running" in raised.value.detail


@pytest.mark.parametrize("body", [{"workflow_runs": []}, {"other": 1}, {"workflow_runs": "not a list"}])
def test_a_missing_path_means_not_ready(respond, body):
    respond(FakeResponse(json_body=body))

    with pytest.raises(NotReady):
        handle_wait_for(payload(path="workflow_runs.0.status"))


def test_path_reads_array_indexes(respond):
    respond(FakeResponse(json_body={"workflow_runs": [{"status": "done"}, {"status": "queued"}]}))

    assert handle_wait_for(payload(path="workflow_runs.0.status"))["status_code"] == 200
    with pytest.raises(NotReady):
        handle_wait_for(payload(path="workflow_runs.1.status"))


@pytest.mark.parametrize("expected", [["done", "skipped"], '["done", "skipped"]'])
def test_expected_can_be_a_list_or_json_array_text(respond, expected):
    respond(FakeResponse(json_body={"status": "done"}))

    assert handle_wait_for(payload(expected=expected))["status_code"] == 200


@pytest.mark.parametrize(
    "actual, expected",
    [(200, "200"), ("200", 200), (1, True), (True, 1)],
)
def test_comparison_is_type_sensitive(respond, actual, expected):
    respond(FakeResponse(json_body={"status": actual}))

    with pytest.raises(NotReady):
        handle_wait_for(payload(expected=expected))


def test_a_number_can_be_expected_from_the_canvas_through_an_array(respond):
    respond(FakeResponse(json_body={"status": 200}))

    assert handle_wait_for(payload(expected="[200]"))["status_code"] == 200


@pytest.mark.parametrize("response", [FakeResponse(404, text="nope"), FakeResponse(302, text="moved")])
def test_a_non_2xx_response_is_a_normal_failure(respond, response):
    respond(response)

    with pytest.raises(RuntimeError, match=str(response.status_code)):
        handle_wait_for(payload())


def test_a_non_json_response_is_a_normal_failure(respond):
    respond(FakeResponse(text="<html>"))

    with pytest.raises(ValueError, match="JSON"):
        handle_wait_for(payload())


@pytest.mark.parametrize("given, used", [(1, 5), (45, 45), (9999, 600), ("20", 20), ("", 30), (None, 30)])
def test_interval_is_clamped(respond, given, used):
    respond(FakeResponse(json_body={"status": "running"}))

    with pytest.raises(NotReady) as raised:
        handle_wait_for(payload(interval_seconds=given))

    assert raised.value.poke_after == used


@pytest.mark.parametrize("given, used", [(0, 1), (120, 120), (999999, 86400), ("", 3600), (None, 3600)])
def test_timeout_is_clamped(given, used):
    assert handler.wait_for_timeout_seconds({"timeout_seconds": given}) == used


@pytest.mark.parametrize(
    "bad",
    [
        {"url": ""},
        {"path": ""},
        {"expected": ""},
        {"expected": None},
        {"expected": []},
        {"expected": "[not json"},
        {"interval_seconds": "soon"},
        {"timeout_seconds": "soon"},
    ],
)
def test_bad_settings_are_rejected(respond, bad):
    respond(FakeResponse(json_body={"status": "done"}))

    with pytest.raises(ValueError):
        handle_wait_for(payload(**bad))


def test_private_urls_are_blocked_before_any_request(respond):
    calls = respond(FakeResponse(json_body={"status": "done"}))

    with pytest.raises(ValueError, match="forbidden"):
        handle_wait_for(payload(url="http://169.254.169.254/latest"))

    assert calls == []


def test_it_is_registered_and_listed():
    from app.tasks.catalog import TASK_TYPE_CATALOG

    assert handler.get_task_handler("wait_for") is handle_wait_for
    assert "wait_for" in {entry["task_type"] for entry in TASK_TYPE_CATALOG}
    assert executor.queue_for_task_type("wait_for") == "celery"


# --- connections ------------------------------------------------------------


def test_connections_are_allowed_in_url_and_headers_only():
    ref = "{{connections.github}}"

    assert misplaced_connection_refs("wait_for", {"url": f"https://x/{ref}", "headers": {"A": ref}}) == []
    assert misplaced_connection_refs("wait_for", {"path": ref, "expected": ref}) == ["expected", "path"]


# --- executor ---------------------------------------------------------------


@pytest.fixture
def worker_db(db_engine, monkeypatch):
    monkeypatch.setattr(executor, "SessionLocal", sessionmaker(bind=db_engine, autoflush=False))


@pytest.fixture
def dispatched(monkeypatch):
    sent: list = []
    monkeypatch.setattr(
        executor, "dispatch_task", lambda task, countdown=None: sent.append((task.id, countdown))
    )
    monkeypatch.setattr(executor, "notify_status_change", lambda *a, **kw: None)
    return sent


def use_handler(monkeypatch, fn):
    monkeypatch.setattr(executor, "get_task_handler", lambda task_type: fn)


def not_ready(poke_after=30, detail="still running"):
    def fn(p):
        raise NotReady(poke_after, detail)

    return fn


def make_sensor(db, *, status=TaskStatus.PENDING, max_retries=3, sensor_payload=None, **extra) -> Task:
    task = Task(
        name="sensor",
        task_type="wait_for",
        payload=sensor_payload if sensor_payload is not None else payload(timeout_seconds=3600),
        max_retries=max_retries,
        status=status,
        created_at=NOW,
        priority=3,
        **extra,
    )
    db.add(task)
    db.commit()
    return task


def due_waiting(db, **extra) -> Task:
    """等了一分鐘、已經到下一次檢查時間的 sensor。"""
    now = datetime.utcnow()
    return make_sensor(
        db,
        status=TaskStatus.WAITING,
        wait_started_at=now - timedelta(minutes=1),
        scheduled_at=now - timedelta(seconds=1),
        **extra,
    )


def logs_of(db, task) -> list[str]:
    rows = db.scalars(select(TaskLog).where(TaskLog.task_id == task.id).order_by(TaskLog.created_at)).all()
    return [row.status for row in rows]


def reload(db, task) -> Task:
    db.expire_all()
    return db.get(Task, task.id)


def sensor_workflow(db, sensor_payload=None, max_retries=0):
    steps = [
        {
            "key": "wait",
            "name": "wait",
            "task_type": "wait_for",
            "payload": sensor_payload if sensor_payload is not None else payload(timeout_seconds=3600),
            "priority": 3,
            "max_retries": max_retries,
        },
        {"key": "next", "name": "next", "task_type": "echo", "payload": {}, "priority": 3, "depends_on": ["wait"]},
    ]
    workflow = create_workflow_from_steps(db, "wf", steps)
    wait, downstream = (
        db.get(
            Task,
            db.scalars(
                select(WorkflowStep.task_id).where(
                    WorkflowStep.workflow_id == workflow.id, WorkflowStep.step_key == key
                )
            ).one(),
        )
        for key in ("wait", "next")
    )
    return workflow, wait, downstream


def test_not_ready_moves_the_task_to_waiting_without_using_a_retry(db, worker_db, dispatched, monkeypatch):
    task = make_sensor(db)
    use_handler(monkeypatch, not_ready(45))
    before = datetime.utcnow()

    execute_task(str(task.id))

    waiting = reload(db, task)
    assert waiting.status == TaskStatus.WAITING
    assert waiting.retry_count == 0
    assert waiting.claimed_at is None
    assert waiting.wait_started_at is not None
    assert waiting.scheduled_at >= before + timedelta(seconds=45)
    assert dispatched == [(task.id, 45)]
    assert logs_of(db, task) == [TaskStatus.WAITING]


def test_later_checks_do_not_add_log_rows(db, worker_db, dispatched, monkeypatch):
    task = due_waiting(db)
    started = task.wait_started_at
    use_handler(monkeypatch, not_ready())

    execute_task(str(task.id))

    again = reload(db, task)
    assert again.status == TaskStatus.WAITING
    assert again.wait_started_at == started
    assert logs_of(db, task) == []


def test_a_waiting_task_that_is_not_due_cannot_be_claimed(db, worker_db, dispatched, monkeypatch):
    # 復原或 broker 重送多出來的訊息：提早到的這一則要直接結束，不能再派送下一次檢查
    task = make_sensor(
        db,
        status=TaskStatus.WAITING,
        wait_started_at=NOW,
        scheduled_at=datetime.utcnow() + timedelta(minutes=5),
    )
    use_handler(monkeypatch, lambda p: pytest.fail("handler must not run"))

    outcome = execute_task(str(task.id))

    assert "was not claimed" in outcome
    assert reload(db, task).status == TaskStatus.WAITING
    assert dispatched == []


def test_two_messages_for_one_check_do_not_start_two_polling_chains(db, worker_db, dispatched, monkeypatch):
    task = due_waiting(db)
    calls: list = []

    def fn(p):
        calls.append(1)
        raise NotReady(30, "still running")

    use_handler(monkeypatch, fn)
    execute_task(str(task.id))
    execute_task(str(task.id))

    assert len(calls) == 1
    assert dispatched == [(task.id, 30)]


def test_success_after_waiting_clears_the_clock_and_runs_downstream(db, worker_db, dispatched, monkeypatch):
    workflow, wait, downstream = sensor_workflow(db)
    now = datetime.utcnow()
    wait.status = TaskStatus.WAITING
    wait.wait_started_at = now - timedelta(minutes=10)
    wait.scheduled_at = now - timedelta(seconds=1)
    db.commit()
    dispatched.clear()
    seen: list = []

    def fn(p):
        seen.append(p["_sensor"]["waited_seconds"])
        return {"status_code": 200, "response_body": {"status": "done"}, "waited_seconds": 600}

    use_handler(monkeypatch, fn)
    execute_task(str(wait.id))

    done = reload(db, wait)
    assert done.status == TaskStatus.SUCCESS
    assert done.wait_started_at is None
    assert seen[0] >= 600
    assert dispatched == [(downstream.id, None)]
    assert logs_of(db, wait) == [TaskStatus.SUCCESS]


def test_the_sensor_clock_is_not_written_into_the_stored_payload(db, worker_db, dispatched, monkeypatch):
    task = make_sensor(db)
    use_handler(monkeypatch, not_ready())

    execute_task(str(task.id))

    assert "_sensor" not in reload(db, task).payload


def test_timeout_fails_without_a_retry_and_cancels_downstream(db, worker_db, dispatched, monkeypatch):
    workflow, wait, downstream = sensor_workflow(db, payload(timeout_seconds=60), max_retries=3)
    now = datetime.utcnow()
    wait.status = TaskStatus.WAITING
    wait.wait_started_at = now - timedelta(seconds=61)
    wait.scheduled_at = now - timedelta(seconds=1)
    db.commit()
    dispatched.clear()
    use_handler(monkeypatch, not_ready())

    with pytest.raises(TimeoutError, match="Timed out"):
        execute_task(str(wait.id))

    failed = reload(db, wait)
    assert failed.status == TaskStatus.FAILED
    assert failed.retry_count == 0
    assert failed.wait_started_at is None
    assert failed.claimed_at is None
    assert reload(db, downstream).status == TaskStatus.CANCELLED
    assert db.get(Workflow, workflow.id).status == WorkFlowStatus.FAILED
    assert dispatched == []
    assert logs_of(db, wait) == [TaskStatus.FAILED]


def test_a_failed_check_retries_and_keeps_the_clock(db, worker_db, dispatched, monkeypatch):
    task = due_waiting(db, max_retries=3)
    started = task.wait_started_at

    def fn(p):
        raise RuntimeError("HTTP 500")

    use_handler(monkeypatch, fn)
    # 直接呼叫時 self.retry 會把例外重新丟出來，不會真的排程
    with pytest.raises(Exception):
        execute_task(str(task.id))

    retrying = reload(db, task)
    assert retrying.status == TaskStatus.RETRYING
    assert retrying.retry_count == 1
    assert retrying.wait_started_at == started


def test_the_first_check_failing_still_starts_the_clock(db, worker_db, dispatched, monkeypatch):
    task = make_sensor(db, max_retries=3)

    def fn(p):
        raise RuntimeError("HTTP 500")

    use_handler(monkeypatch, fn)
    with pytest.raises(Exception):
        execute_task(str(task.id))

    assert reload(db, task).wait_started_at is not None


def test_running_out_of_retries_clears_the_clock(db, worker_db, dispatched, monkeypatch):
    task = due_waiting(db, max_retries=0)

    def fn(p):
        raise RuntimeError("HTTP 500")

    use_handler(monkeypatch, fn)
    with pytest.raises(RuntimeError):
        execute_task(str(task.id))

    failed = reload(db, task)
    assert failed.status == TaskStatus.FAILED
    assert failed.wait_started_at is None


def test_secrets_are_masked_in_the_waiting_log(db, worker_db, dispatched, monkeypatch):
    task = make_sensor(db)
    monkeypatch.setattr(executor, "resolve_connections", lambda db, t: (t.payload, {"github": "s3cret"}))
    use_handler(monkeypatch, not_ready(detail="status is s3cret"))

    execute_task(str(task.id))

    log = db.scalars(select(TaskLog).where(TaskLog.task_id == task.id)).one()
    assert log.result["detail"] == "status is <connection:github>"


def test_secrets_are_masked_in_the_timeout_message(db, worker_db, dispatched, monkeypatch):
    task = due_waiting(db, sensor_payload=payload(timeout_seconds=1))
    monkeypatch.setattr(executor, "resolve_connections", lambda db, t: (t.payload, {"github": "s3cret"}))
    use_handler(monkeypatch, not_ready(detail="status is s3cret"))

    with pytest.raises(TimeoutError) as raised:
        execute_task(str(task.id))

    assert "s3cret" not in str(raised.value)
    log = db.scalars(select(TaskLog).where(TaskLog.task_id == task.id)).one()
    assert "s3cret" not in log.error_message


# --- 復原 --------------------------------------------------------------------


def test_recovery_resends_only_overdue_waiting_tasks(db, dispatched):
    overdue = make_sensor(db, status=TaskStatus.WAITING, wait_started_at=NOW, scheduled_at=NOW - timedelta(minutes=6))
    not_due = make_sensor(db, status=TaskStatus.WAITING, wait_started_at=NOW, scheduled_at=NOW + timedelta(seconds=30))
    in_grace = make_sensor(db, status=TaskStatus.WAITING, wait_started_at=NOW, scheduled_at=NOW - timedelta(minutes=4))
    running = make_sensor(db, status=TaskStatus.RUNNING, claimed_at=NOW, scheduled_at=NOW - timedelta(hours=1))

    assert recover_lost_waiting_tasks(db, NOW) == 1

    assert dispatched == [(overdue.id, None)]
    assert reload(db, overdue).status == TaskStatus.WAITING
    assert reload(db, not_due).scheduled_at == NOW + timedelta(seconds=30)
    assert reload(db, in_grace).status == TaskStatus.WAITING
    assert reload(db, running).status == TaskStatus.RUNNING


def test_recovery_does_not_resend_every_minute_while_workers_are_down(db, dispatched):
    make_sensor(db, status=TaskStatus.WAITING, wait_started_at=NOW, scheduled_at=NOW - timedelta(minutes=6))

    assert recover_lost_waiting_tasks(db, NOW) == 1
    assert recover_lost_waiting_tasks(db, NOW + timedelta(minutes=1)) == 0
    assert recover_lost_waiting_tasks(db, NOW + timedelta(minutes=6)) == 1


def test_recovery_ignores_deleted_tasks(db, dispatched):
    make_sensor(
        db, status=TaskStatus.WAITING, wait_started_at=NOW, scheduled_at=NOW - timedelta(minutes=6), deleted_at=NOW
    )

    assert recover_lost_waiting_tasks(db, NOW) == 0
    assert dispatched == []


def test_a_resent_task_can_be_claimed_again(db, worker_db, dispatched, monkeypatch):
    now = datetime.utcnow()
    task = make_sensor(
        db, status=TaskStatus.WAITING, wait_started_at=now - timedelta(minutes=10), scheduled_at=now - timedelta(minutes=6)
    )
    recover_lost_waiting_tasks(db, now)
    use_handler(monkeypatch, lambda p: {"status_code": 200})

    execute_task(str(task.id))

    assert reload(db, task).status == TaskStatus.SUCCESS


def test_running_recovery_leaves_waiting_tasks_alone(db, dispatched):
    task = make_sensor(
        db, status=TaskStatus.WAITING, wait_started_at=NOW, scheduled_at=NOW, claimed_at=NOW - timedelta(hours=1)
    )

    assert recover_stale_running_tasks(db, NOW) == 0
    assert reload(db, task).status == TaskStatus.WAITING
    assert dispatched == []


def test_the_beat_entry_point_also_recovers_waiting_tasks(db, worker_db, dispatched):
    now = datetime.utcnow()
    task = make_sensor(
        db, status=TaskStatus.WAITING, wait_started_at=now - timedelta(hours=1), scheduled_at=now - timedelta(minutes=6)
    )

    assert executor.recover_stale_tasks() == 1
    assert dispatched == [(task.id, None)]


def test_retrying_the_workflow_restarts_the_sensor_clock(db, dispatched):
    workflow, wait, downstream = sensor_workflow(db)
    wait.status = TaskStatus.FAILED
    wait.wait_started_at = NOW
    downstream.status = TaskStatus.CANCELLED
    workflow.status = WorkFlowStatus.FAILED
    db.commit()
    dispatched.clear()

    assert retry_workflow_from_failure(db, workflow) == 2

    reset = reload(db, wait)
    assert reset.status == TaskStatus.PENDING
    assert reset.wait_started_at is None
    assert dispatched == [(wait.id, None)]
