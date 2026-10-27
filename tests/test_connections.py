# ---------------------------------------------------
# Coworkify — connections: encrypted secrets referenced as {{connections.<name>}}
#
# What has to hold:
#   - the value is encrypted at rest and never comes back out of the API;
#   - only the owner can see, rotate, delete — or use — a connection;
#   - the plaintext exists only in the payload handed to the handler: the
#     stored task payload keeps the placeholder, and results / error messages
#     are scrubbed before they reach task_logs;
#   - references are only allowed in fields that make network requests,
#     never in python / shell code.
# ---------------------------------------------------

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.connection import Connection
from app.models.task import Task, TaskStatus
from app.models.task_log import TaskLog
from app.tasks import executor
from app.tasks.executor import execute_task

TOKEN = "ghp_secretTOKEN1234567890"


@pytest.fixture(autouse=True)
def connections_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CONNECTIONS_KEY", key)
    return key


def create(client, auth, name="github", value=TOKEN, **extra):
    return client.post("/connections/", json={"name": name, "value": value, **extra}, headers=auth)


# --- API ---------------------------------------------------------------------------


def test_the_value_is_encrypted_at_rest_and_never_returned(client, auth, db):
    res = create(client, auth, description="repo read")
    assert res.status_code == 201
    assert "value" not in res.json()
    assert TOKEN not in res.text
    assert TOKEN not in client.get("/connections/", headers=auth).text

    stored = db.scalars(select(Connection)).one()
    assert TOKEN not in stored.encrypted_value


def test_names_are_unique_per_user_and_follow_step_key_rules(client, auth, other_auth):
    assert create(client, auth).status_code == 201
    assert create(client, auth).status_code == 409
    assert create(client, other_auth).status_code == 201  # 另一個使用者可以用同名
    assert create(client, auth, name="has space").status_code == 422


def test_a_connection_can_be_rotated_and_deleted(client, auth, db):
    conn = create(client, auth).json()

    res = client.patch(f"/connections/{conn['id']}", json={"value": "ghp_rotated"}, headers=auth)
    assert res.status_code == 200
    from app.core.connection_crypto import decrypt
    db.expire_all()
    assert decrypt(db.get(Connection, conn["id"]).encrypted_value) == "ghp_rotated"

    assert client.delete(f"/connections/{conn['id']}", headers=auth).status_code == 204
    assert client.get("/connections/", headers=auth).json() == []


def test_someone_elses_connection_is_invisible(client, auth, other_auth):
    conn = create(client, auth).json()
    assert client.get("/connections/", headers=other_auth).json() == []
    assert client.patch(f"/connections/{conn['id']}", json={"value": "x"}, headers=other_auth).status_code == 404
    assert client.delete(f"/connections/{conn['id']}", headers=other_auth).status_code == 404


def test_a_missing_key_is_a_clear_503(client, auth, monkeypatch):
    monkeypatch.delenv("CONNECTIONS_KEY")
    res = create(client, auth)
    assert res.status_code == 503
    assert "CONNECTIONS_KEY" in res.json()["detail"]


def test_the_key_can_be_rotated_without_losing_stored_values(client, auth, db, monkeypatch, connections_key):
    create(client, auth)
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("CONNECTIONS_KEY", f"{new_key},{connections_key}")

    from app.core.connection_crypto import decrypt
    assert decrypt(db.scalars(select(Connection)).one().encrypted_value) == TOKEN


# --- 在哪裡可以用 -----------------------------------------------------------------------


def test_references_are_only_accepted_in_request_fields(client, auth):
    ok = {"key": "a", "name": "a", "task_type": "http_request",
          "payload": {"url": "https://api.github.com/x", "headers": {"Authorization": "Bearer {{connections.github}}"}}}
    leak = {"key": "b", "name": "b", "task_type": "python",
            "payload": {"code": "def main():\n    return '{{connections.github}}'"}}

    assert client.post("/definitions/", json={"name": "ok", "steps": [ok]}, headers=auth).status_code == 201
    res = client.post("/definitions/", json={"name": "leak", "steps": [leak]}, headers=auth)
    assert res.status_code == 422
    assert "connections" in res.text


# --- 執行時 ----------------------------------------------------------------------------


@pytest.fixture
def run_as_worker(client, db_engine, monkeypatch):
    """execute_task 在測試裡直接呼叫，自己開的 session 指到測試資料庫。"""
    monkeypatch.setattr(executor, "SessionLocal", sessionmaker(bind=db_engine, autoflush=False))
    seen = []

    def use(handler):
        def capture(task_type):
            def wrapped(payload):
                seen.append(payload)
                return handler(payload)
            return wrapped
        monkeypatch.setattr(executor, "get_task_handler", capture)
        return seen
    return use


def make_task(client, auth, payload, task_type="http_request", max_retries=0):
    res = client.post("/tasks/", json={"name": "t", "task_type": task_type, "payload": payload,
                                       "max_retries": max_retries}, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()["id"]


AUTH_PAYLOAD = {"url": "https://api.github.com/user", "headers": {"Authorization": "Bearer {{connections.github}}"}}


def test_the_handler_gets_the_secret_but_nothing_stored_does(client, auth, db, run_as_worker):
    create(client, auth)
    task_id = make_task(client, auth, AUTH_PAYLOAD)
    # 回應裡剛好回顯了 token——結果存進 task_logs 前要遮掉
    seen = run_as_worker(lambda p: {"status_code": 200, "response_body": {"echo": p["headers"]["Authorization"]}})

    execute_task(task_id)

    assert seen[0]["headers"]["Authorization"] == f"Bearer {TOKEN}"
    db.expire_all()
    task = db.get(Task, task_id)
    assert task.status == TaskStatus.SUCCESS
    assert task.payload == AUTH_PAYLOAD  # 資料庫裡還是佔位字串
    (log,) = db.scalars(select(TaskLog).where(TaskLog.task_id == task.id)).all()
    assert TOKEN not in str(log.result)
    assert log.result["response_body"]["echo"] == "Bearer <connection:github>"


def test_an_error_message_never_carries_the_secret(client, auth, db, run_as_worker):
    create(client, auth, name="hook", value="https://discord.com/api/webhooks/123/very-secret")
    task_id = make_task(client, auth, {"webhook_url": "{{connections.hook}}", "message": "hi"}, task_type="notify")

    def boom(payload):
        raise RuntimeError(f"404 Client Error: Not Found for url: {payload['webhook_url']}")
    run_as_worker(boom)

    with pytest.raises(RuntimeError) as exc:
        execute_task(task_id)

    assert "very-secret" not in str(exc.value)
    db.expire_all()
    (log,) = db.scalars(select(TaskLog).where(TaskLog.task_id == task_id)).all()
    assert log.status == TaskStatus.FAILED
    assert "very-secret" not in log.error_message
    assert "<connection:hook>" in log.error_message


def test_an_unknown_or_someone_elses_connection_fails_the_step(client, auth, other_auth, db, run_as_worker):
    create(client, other_auth)  # mallory 有 github，alice 沒有
    task_id = make_task(client, auth, AUTH_PAYLOAD)
    run_as_worker(lambda p: pytest.fail("handler must not run"))

    with pytest.raises(ValueError, match="Connection not found: github"):
        execute_task(task_id)
    db.expire_all()
    assert db.get(Task, task_id).status == TaskStatus.FAILED


def test_a_single_task_cannot_smuggle_a_secret_into_code(client, auth, db, run_as_worker):
    create(client, auth)
    task_id = make_task(client, auth, {"code": "print('{{connections.github}}')"}, task_type="python")
    run_as_worker(lambda p: pytest.fail("handler must not run"))

    with pytest.raises(ValueError, match="not in python steps"):
        execute_task(task_id)
