# ---------------------------------------------------
# Coworkify — every resource belongs to the user who created it
#
# Definitions, runs, tasks and schedules are only visible to their owner.
# Another user gets the same 404 as for an id that doesn't exist — a 403
# would confirm the id is real. Ownership also has to follow the things the
# system creates on a user's behalf: the tasks of a run, the tasks a
# for_each expands into, and the runs a schedule triggers.
#
# `auth` is alice, `other_auth` is mallory (see conftest.py).
# ---------------------------------------------------

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.models.schedule import WorkflowSchedule
from app.models.task import Task
from app.models.user import User
from app.models.workflow import Workflow
from app.tasks.executor import record_task_success
from app.tasks.scheduler import run_due_schedules

STEPS = [
    {"key": "input_1", "name": "input", "task_type": "input", "payload": {"data": [1, 2]}},
    {"key": "each", "name": "each", "task_type": "echo", "for_each": "input_1"},
]


@pytest.fixture
def alices(client, auth):
    """alice 的一條定義、一次 run、一個單獨的 task、一個排程。"""
    definition = client.post("/definitions/", json={"name": "alice's", "steps": STEPS}, headers=auth).json()
    run = client.post(f"/definitions/{definition['id']}/runs", json={}, headers=auth).json()
    task = client.post("/tasks/", json={"name": "solo", "task_type": "echo"}, headers=auth).json()
    schedule = client.post("/schedules/", json={
        "name": "hourly", "cron_expression": "5 * * * *", "definition_id": definition["id"],
    }, headers=auth).json()
    return {"definition": definition, "run": run, "task": task, "schedule": schedule}


# --- 看不到 -----------------------------------------------------------------------


def test_lists_only_show_your_own(client, alices, other_auth):
    for path in ("/definitions/", "/workflows/", "/tasks/", "/schedules/"):
        assert client.get(path, headers=other_auth).json() == [], path


def test_lists_still_show_the_owner_everything(client, alices, auth):
    assert len(client.get("/definitions/", headers=auth).json()) == 1
    assert len(client.get("/workflows/", headers=auth).json()) == 1
    assert len(client.get("/schedules/", headers=auth).json()) == 1
    # 單獨建立的 task 加上 run 裡的 input_1
    assert len(client.get("/tasks/", headers=auth).json()) == 2


def test_someone_elses_resources_are_404(client, alices, other_auth):
    d, r, t, s = (alices[k]["id"] for k in ("definition", "run", "task", "schedule"))
    for path in (
        f"/definitions/{d}", f"/definitions/{d}/runs",
        f"/workflows/{r}",
        f"/tasks/{t}", f"/tasks/{t}/logs", f"/tasks/{t}/result",
        f"/schedules/{s}",
    ):
        assert client.get(path, headers=other_auth).status_code == 404, path


# --- 改不了 -----------------------------------------------------------------------


def test_someone_elses_resources_cannot_be_changed(client, alices, auth, other_auth):
    d, r, t, s = (alices[k]["id"] for k in ("definition", "run", "task", "schedule"))
    attempts = [
        client.put(f"/definitions/{d}", json={"name": "mine now", "steps": STEPS}, headers=other_auth),
        client.post(f"/definitions/{d}/runs", json={}, headers=other_auth),
        client.post(f"/workflows/{r}/rerun", headers=other_auth),
        client.post(f"/workflows/{r}/retry", headers=other_auth),
        client.post(f"/workflows/{r}/promote-to-schedule",
                    json={"name": "x", "cron_expression": "0 3 * * *"}, headers=other_auth),
        client.patch(f"/schedules/{s}", json={"enabled": False}, headers=other_auth),
        client.delete(f"/schedules/{s}", headers=other_auth),
        client.delete(f"/workflows/{r}", headers=other_auth),
        client.delete(f"/tasks/{t}", headers=other_auth),
    ]
    assert [a.status_code for a in attempts] == [404] * len(attempts)

    # 對 alice 來說一切原封不動
    assert client.get(f"/definitions/{d}", headers=auth).json()["name"] == "alice's"
    assert client.get(f"/schedules/{s}", headers=auth).json()["enabled"] is True
    assert client.get(f"/workflows/{r}", headers=auth).status_code == 200
    assert client.get(f"/tasks/{t}", headers=auth).status_code == 200
    assert len(client.get("/workflows/", headers=auth).json()) == 1


def test_you_cannot_schedule_someone_elses_definition(client, alices, other_auth):
    res = client.post("/schedules/", json={
        "name": "sneaky", "cron_expression": "5 * * * *", "definition_id": alices["definition"]["id"],
    }, headers=other_auth)
    assert res.status_code == 400


# --- 系統代替使用者建立的東西，也要歸對人 -------------------------------------------------


def alice_id(db):
    return db.scalars(select(User.id).where(User.username == "alice")).one()


def test_a_runs_tasks_and_expanded_tasks_belong_to_the_runner(client, alices, db):
    run = db.get(Workflow, alices["run"]["id"])
    root = db.get(Task, alices["run"]["steps"][0]["task_id"])
    record_task_success(db, root, [1, 2])  # for_each 展開成 2 個 task

    owners = {t.created_by for t in db.scalars(
        select(Task).where(Task.name.like("each [%]"))
    ).all()}
    assert run.created_by == alice_id(db)
    assert owners == {alice_id(db)}


def test_a_scheduled_run_belongs_to_the_schedules_owner(client, alices, db, monkeypatch):
    schedule = db.get(WorkflowSchedule, alices["schedule"]["id"])
    schedule.next_run_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    assert run_due_schedules(db, datetime.utcnow()) == 1

    runs = db.scalars(select(Workflow).where(Workflow.definition_id == schedule.definition_id)).all()
    assert len(runs) == 2
    assert {r.created_by for r in runs} == {alice_id(db)}


# --- WebSocket ------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["", "?token=not-a-jwt"])
def test_the_websocket_requires_a_valid_token(client, query):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/tasks{query}") as ws:
            ws.receive_text()
    assert exc.value.code == 1008
