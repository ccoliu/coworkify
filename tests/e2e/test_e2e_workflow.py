# ---------------------------------------------------
# Coworkify — end-to-end smoke tests against a running stack (issue #7)
#
# Everything else in tests/ replaces Celery and Redis. These do not: they
# talk to a live API over HTTP and WebSocket, and a real Celery worker
# consumes the real Redis broker and runs the handlers. They cover what the
# in-process tests cannot see — broker routing, `self.retry` backoff,
# chained dispatch between separate worker processes, the join claim under
# real concurrency, and Pub/Sub delivery to /ws/tasks.
#
# Skipped unless E2E_BASE_URL points at the API, e.g.
#   E2E_BASE_URL=http://localhost:8000 pytest tests/e2e -q
# CI runs them in their own job (see .github/workflows/ci.yml, job "e2e").
# Each test registers its own user and creates its own definitions.
# ---------------------------------------------------

from __future__ import annotations

import json
import os
import time
import uuid

import httpx
import pytest

BASE_URL = os.getenv("E2E_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="set E2E_BASE_URL to run against a live API and worker")

TIMEOUT_SECONDS = 90


def register():
    client = httpx.Client(base_url=BASE_URL, timeout=10)
    res = client.post(
        "/auth/register",
        json={"username": f"e2e-{uuid.uuid4().hex[:10]}", "password": "e2e-password"},
    )
    assert res.status_code == 201, res.text
    client.token = res.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {client.token}"
    return client


@pytest.fixture(scope="module")
def api():
    client = register()
    yield client
    client.close()


@pytest.fixture(scope="module")
def other_api():
    client = register()
    yield client
    client.close()

def poll(fetch, done, what):
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while True:
        value = fetch()
        if done(value):
            return value
        if time.monotonic() > deadline:
            pytest.fail(f"{what} did not finish within {TIMEOUT_SECONDS}s: {value}")
        time.sleep(.5)


def run_to_completion(api, steps):
    definition = api.post("/definitions/", json={"name": "e2e", "steps": steps})
    assert definition.status_code == 201, definition.text
    run = api.post(f"/definitions/{definition.json() ['id']}/runs", json={"input": {}})
    assert run.status_code == 201, run.text
    return poll(
        lambda: api.get(f"/workflows/{run.json()['id']}").json(),
        lambda w: w["status"] in {"success", "failed"},
        "workflow",
    )

def step(run, key):
    return next(s for s in run["steps"] if s["step_key"] == key)


def test_a_branching_fan_out_workflow_runs_to_completion(api):
    steps = [
        {"key": "input_1", "name": "input", "task_type": "input", "payload": {"data": {"numbers": [1, 2, 3]}}},
        {"key": "items", "name": "items", "task_type": "python", "depends_on": ["input_1"],
         "payload": {"code": "def main():\n    return inputs['input_1']['numbers']"}},
        {"key": "square", "name": "square", "task_type": "python", "for_each": "items",
         "payload": {"code": "def main():\n    return {{item}} * {{item}}"}},
        {"key": "total", "name": "total", "task_type": "python", "reduce_of": "square",
         "payload": {"code": "def main():\n    return sum(inputs['square'])"}},
        # 沒填 left：自動帶入唯一上游 total 的回傳值（1 + 4 + 9 = 14）
        {"key": "check", "name": "check", "task_type": "condition", "depends_on": ["total"],
         "payload": {"operator": "gt", "right": 10}},
        {"key": "big", "name": "big", "task_type": "shell", "depends_on": ["check"],
         "branch_of": "check", "branch_when": "true",
         "payload": {"command": "echo big $(./get_input total)"}},
        {"key": "small", "name": "small", "task_type": "shell", "depends_on": ["check"],
         "branch_of": "check", "branch_when": "false", "payload": {"command": "echo small"}},
    ]

    run = run_to_completion(api, steps)

    assert run["status"] == "success", run
    assert step(run, "small")["task_status"] == "cancelled"
    assert run["result"]["big"]["stdout"].strip() == "big 14"
    squares = [s for s in run["steps"] if s["task_name"].startswith("square [")]
    assert len(squares) == 3 and all(s["task_status"] == "success" for s in squares)


def test_a_join_runs_once_when_its_upstreams_finish_together(api):
    # worker 的 concurrency 是 2：a、b 同時在兩個 process 裡跑完，兩邊都可能派送 join
    steps = [
        {"key": "a", "name": "a", "task_type": "python", "payload": {"code": "def main():\n    return 'a'"}},
        {"key": "b", "name": "b", "task_type": "python", "payload": {"code": "def main():\n    return 'b'"}},
        {"key": "join", "name": "join", "task_type": "python", "depends_on": ["a", "b"],
         "payload": {"code": "def main():\n    return inputs['a'] + inputs['b']"}},  
    ]

    run = run_to_completion(api, steps)

    assert run["status"] == "success", run
    logs = api.get(f"/tasks/{step(run, 'join')['task_id']}/logs").json()
    assert [log["status"] for log in logs] == ["success"]

def test_a_failing_task_is_retried_with_backoff_then_fails(api):
    created = api.post("/tasks/", json = {
        "name": "always fails", "task_type": "python", "max_retries": 1,
        "payload": {"code": "def main():\n    raise RuntimeError('boom')"},
    }).json()

    task = poll(
        lambda: api.get(f"/tasks/{created['id']}").json(),
        lambda t: t["status"] == "failed",
        "failing task"
    )

    assert task["retry_count"] == 1
    logs = api.get(f"/tasks/{created['id']}/logs").json()
    assert [log["status"] for log in logs] == ["retrying", "failed"]
    assert "boom" in logs[-1]["error_message"]

def test_status_changes_are_pushed_over_the_websocket_to_their_owner_only(api, other_api):
    from websockets.sync.client import connect

    ws_url = BASE_URL.replace("http", "ws", 1) + f"/ws/tasks?token={api.token}"
    with connect(ws_url) as ws:
        # 伺服器在 accept 之後才訂閱 Redis 頻道，先等它訂好，免得漏掉最早的事件
        time.sleep(1)
        # 別人的 task 先建立、先跑完：如果會被推過來，一定會在自己的事件之前出現
        theirs = other_api.post("/tasks/", json={"name": "not yours", "task_type": "echo"}).json()
        poll(lambda: other_api.get(f"/tasks/{theirs['id']}").json(), lambda t: t["status"] == "success", "other task")
        mine = api.post("/tasks/", json={"name": "ping", "task_type": "echo", "payload": {"message": "hi"}}).json()

        seen = []
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while ("success", mine["id"]) not in seen:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pytest.fail(f"no success event for task {mine['id']}; saw {seen}")
            event = json.loads(ws.recv(timeout=remaining))
            seen.append((event["status"], event["task_id"]))

    assert seen == [("running", mine["id"]), ("success", mine["id"])]


def test_the_websocket_refuses_a_connection_without_a_token():
    from websockets.exceptions import InvalidStatus
    from websockets.sync.client import connect

    # 伺服器在 accept 之前就關閉，對真正的 client 來說是握手被拒（HTTP 403）
    with pytest.raises(InvalidStatus) as exc:
        connect(BASE_URL.replace("http", "ws", 1) + "/ws/tasks")
    assert exc.value.response.status_code == 403