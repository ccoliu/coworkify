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


@pytest.fixture(scope="module")
def api():
    client = httpx.Client(base_url=BASE_URL, timeout=10)
    res = client.post(
        "/auth/register",
        json={"username": f"e2e-{uuid.uuid4().hex[:10]}", "password": "e2e-password"}
    )
    assert res.status_code == 201, res.text
    client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
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

def test_status_changes_are_pushed_over_the_websocket(api):
    from websockets.sync.client import connect

    ws_url = BASE_URL.replace("http", "ws", 1) + "/ws/tasks"
    with connect(ws_url) as ws:
        # 伺服器在 accept 之後才訂閱 Redis 頻道，先等它訂好，免得漏掉最早的事件
        time.sleep(1)
        task = api.post("/tasks/", json={"name": "ping", "task_type": "echo", "payload": {"message": "hi"}}).json()

        seen = []
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while "success" not in seen:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pytest.fail(f"no success sent for task {task['id']}; saw {seen}")
            event = json.loads(ws.recv(timeout=remaining))
            if event["task_id"] == task["id"]:
                seen.append(event["status"])
        
    assert seen == ["running", "success"]