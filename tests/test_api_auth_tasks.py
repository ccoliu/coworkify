# ---------------------------------------------------
# Coworkify — API: auth, rate limiting, and single tasks (issue #4)
#
# These go through the real FastAPI app with TestClient: routing, request
# validation, auth dependencies and response models all run. Only the edges
# are replaced (see the `client` fixture in conftest.py): the database is the
# test database, Celery dispatch is recorded instead of sent, and the rate
# limiter's Redis is a fake.
# ---------------------------------------------------

from __future__ import annotations

from sqlalchemy import select

from app.models.task import Task, TaskStatus
from app.tasks.executor import record_task_failure


# --- auth -------------------------------------------------------------------

def test_register_returns_a_token_that_identifies_the_user(client):
    res = client.post("/auth/register", json={"username": "alice", "password": "correct-horse"})
    assert res.status_code == 201
    token = res.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

def test_a_username_can_only_be_registered_once(client, auth):
    res = client.post("/auth/register", json={"username": "alice", "password": "another-pass"})
    assert res.status_code == 409

def test_login_checks_the_password(client, auth):
    ok = client.post("/auth/login", json={"username": "alice", "password": "correct-horse"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    wrong = client.post("/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert wrong.status_code == 401

def test_protected_endpoints_reject_missng_and_invalid_tokens(client):
    assert client.get("/tasks/").status_code == 401
    bad = client.get("/tasks/", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401

def test_requests_over_the_rate_limit_get_429(client, auth):
    client.fake_redis.requests_in_window = 5000 # /tasks 的上限是每秒 5000 次

    res = client.get("/tasks/", headers=auth)
    assert res.status_code == 429
    assert res.headers.get("Retry-After") == "1"

# --- tasks ------------------------------------------------------------------

def create_task(client, auth, **overrides):
    body = {"name": "hello", "task_type": "echo", "payload": {"message": "hi"}, **overrides}
    res = client.post("/tasks/", json=body, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()

def test_a_new_task_is_pending_and_dispatched(client, auth):
    task = create_task(client, auth, priority=2)

    assert task["status"] == TaskStatus.PENDING
    assert task["priority"] == 2
    assert [str(t) for t in client.dispatched] == [task["id"]]
    assert client.get(f"/tasks/{task['id']}", headers=auth).json()["name"] == "hello"

def test_a_task_with_scheduled_at_is_queued_for_later_instead(client, auth):
    task = create_task(client, auth, scheduled_at="2030-01-01T09:00:00")

    assert client.dispatched == []
    ((args, options),) = client.scheduled
    assert args == [task["id"]]
    assert options["eta"].isoformat() == "2030-01-01T09:00:00"

def test_priority_outside_0_to_9_is_rejected(client, auth):
    res = client.post("/tasks/", json={"name": "x", "task_type": "echo", "priority": 10}, headers=auth)
    assert res.status_code == 422

def test_tasks_can_be_filtered_by_status(client, auth, db):
    done = create_task(client, auth, name="done")
    create_task(client, auth, name="waiting")
    db.get(Task, done["id"]).status = TaskStatus.SUCCESS
    db.commit()

    res = client.get("/tasks/", params={"status": "success"}, headers=auth)
    assert [t["name"] for t in res.json()] == ["done"]

def test_a_deleted_task_disappears_but_its_row_is_kept(client, auth, db):
    task = create_task(client, auth)

    assert client.delete(f"/tasks/{task['id']}", headers=auth).status_code == 204
    assert client.get(f"/tasks/{task['id']}", headers=auth).status_code == 404
    assert client.get("/tasks/", headers=auth).json() == []
    #soft delete
    db.expire_all()
    assert db.get(Task, task["id"]) is not None


def test_a_task_inside_a_workflow_cannot_be_deleted_on_its_own(client, auth):
    run = client.post(
        "/workflows/",
        json={"name": "wf", "steps": [{"key": "a", "name": "a", "task_type": "echo"}]},
        headers=auth,
    ).json()
    task_id = run["steps"][0]["task_id"]

    assert client.delete(f"/tasks/{task_id}", headers=auth).status_code == 400

def test_unknown_task_ids_are_404(client, auth):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/tasks/{missing}", headers=auth).status_code == 404
    assert client.get(f"/tasks/{missing}/logs", headers=auth).status_code == 404
    assert client.delete(f"/tasks/{missing}", headers=auth).status_code == 404

def test_logs_list_every_attempt_oldest_first(client, auth, db):
    created = create_task(client, auth, max_retries=1)
    task = db.get(Task, created["id"])
    record_task_failure(db, task, "first try")   # 還有一次重試 → RETRYING
    record_task_failure(db, task, "second try")  # 用完 → FAILED

    logs = client.get(f"/tasks/{created['id']}/logs", headers=auth).json()
    assert [log["status"] for log in logs] == ["retrying", "failed"]
    assert "first try" in logs[0]["error_message"]

    result = client.get(f"/tasks/{created['id']}/result", headers=auth).json()
    assert result["status"] == "failed"
    assert "second try" in result["error_message"]

def test_the_task_type_catalog_lists_the_builder_types(client, auth):
    types = {t["task_type"] for t in client.get("/tasks/types", headers=auth).json()}
    assert {"input", "python", "shell", "http_request", "condition", "agent_step", "notify"} <= types