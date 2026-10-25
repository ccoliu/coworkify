# ---------------------------------------------------
# Coworkify — API: definitions, runs, rerun/retry, and schedules (issue #4)
#
# Same setup as test_api_auth_tasks.py: the real FastAPI app through
# TestClient, against the test database, with Celery dispatch recorded.
# These cover the paths a user actually clicks through: build a definition,
# run it with input (and get 422 for bad input), edit it (version bump only
# when something that affects a run changed), re-run or resume a run, and
# turn it into a cron schedule.
# ---------------------------------------------------

from __future__ import annotations

from datetime import datetime

from app.core.cron import compute_next_run
from app.models.task import Task
from app.tasks.executor import record_task_failure, record_task_success

STEPS = [
    {"key": "input_1", "name": "input", "task_type": "input", "payload": {"data": {}}},
    {"key": "work", "name": "work", "task_type": "echo", "depends_on": ["input_1"]},
]
SCHEMA = [
    {"key": "repo", "label": "Repository", "kind": "string", "required": True},
    {"key": "hours", "label": "Hours", "kind": "number", "default": 24},
]


def create_definition(client, auth, *, steps=STEPS, input_schema=SCHEMA, name="triage"):
    res = client.post(
        "/definitions/",
        json={"name": name, "steps": steps, "input_schema": input_schema},
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return res.json()


def start_run(client, auth, definition, input):
    res = client.post(f"/definitions/{definition['id']}/runs", json={"input": input}, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()


def step_task_id(run, key):
    return next(s["task_id"] for s in run["steps"] if s["step_key"] == key)


# --- definitions --------------------------------------------------------------


def test_a_new_definition_starts_at_version_1_with_no_runs(client, auth):
    definition = create_definition(client, auth)

    assert definition["version"] == 1
    assert definition["run_count"] == 0
    assert [s["key"] for s in definition["steps"]] == ["input_1", "work"]


def test_an_invalid_graph_is_rejected(client, auth):
    steps = [{"key": "a", "name": "a", "task_type": "echo", "depends_on": ["missing"]}]
    res = client.post("/definitions/", json={"name": "bad", "steps": steps}, headers=auth)
    assert res.status_code == 422


def test_put_bumps_the_version_only_when_steps_or_schema_change(client, auth):
    definition = create_definition(client, auth)
    url = f"/definitions/{definition['id']}"

    renamed = client.put(url, json={"name": "renamed", "steps": STEPS, "input_schema": SCHEMA}, headers=auth)
    assert renamed.json()["version"] == 1
    assert renamed.json()["name"] == "renamed"

    new_steps = STEPS + [{"key": "more", "name": "more", "task_type": "echo", "depends_on": ["work"]}]
    changed = client.put(url, json={"name": "renamed", "steps": new_steps, "input_schema": SCHEMA}, headers=auth)
    assert changed.json()["version"] == 2


def test_unknown_definitions_are_404(client, auth):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/definitions/{missing}", headers=auth).status_code == 404
    assert client.post(f"/definitions/{missing}/runs", json={}, headers=auth).status_code == 404


# --- runs ---------------------------------------------------------------------


def test_a_run_validates_its_input_and_fills_defaults(client, auth):
    definition = create_definition(client, auth)
    run = start_run(client, auth, definition, {"repo": "apache/airflow"})

    assert run["input"] == {"repo": "apache/airflow", "hours": 24}
    assert run["definition_version"] == 1
    # 只有根節點被派送；work 要等 input_1
    assert [str(t) for t in client.dispatched] == [step_task_id(run, "input_1")]

    listed = client.get(f"/definitions/{definition['id']}", headers=auth).json()
    assert listed["run_count"] == 1
    assert listed["last_run"]["id"] == run["id"]


def test_a_run_with_bad_input_is_422_and_says_why(client, auth):
    definition = create_definition(client, auth)
    res = client.post(f"/definitions/{definition['id']}/runs", json={"input": {"hours": "soon"}}, headers=auth)

    assert res.status_code == 422
    assert "Repository" in res.json()["detail"]
    assert "Hours" in res.json()["detail"]
    assert client.get(f"/definitions/{definition['id']}/runs", headers=auth).json() == []


def test_input_is_refused_when_the_definition_declares_none(client, auth):
    definition = create_definition(client, auth, input_schema=[])
    res = client.post(f"/definitions/{definition['id']}/runs", json={"input": {"repo": "x"}}, headers=auth)
    assert res.status_code == 400


def test_rerun_creates_a_new_run_with_the_same_input(client, auth):
    definition = create_definition(client, auth)
    first = start_run(client, auth, definition, {"repo": "x"})

    res = client.post(f"/workflows/{first['id']}/rerun", headers=auth)
    assert res.status_code == 201
    second = res.json()
    assert second["id"] != first["id"]
    assert second["input"] == first["input"]
    assert second["definition_id"] == definition["id"]
    assert client.get(f"/workflows/{first['id']}", headers=auth).status_code == 200


def test_retry_resumes_a_failed_run_in_place(client, auth, db):
    definition = create_definition(client, auth)
    run = start_run(client, auth, definition, {"repo": "x"})
    root = db.get(Task, step_task_id(run, "input_1"))
    record_task_success(db, root, {"repo": "x"})
    work = db.get(Task, step_task_id(run, "work"))
    work.max_retries = 0
    record_task_failure(db, work, "boom")
    client.dispatched.clear()

    res = client.post(f"/workflows/{run['id']}/retry", headers=auth)

    assert res.status_code == 200
    assert res.json()["id"] == run["id"]
    assert res.json()["status"] == "pending"
    assert [str(t) for t in client.dispatched] == [step_task_id(run, "work")]


def test_only_a_failed_run_can_be_retried(client, auth):
    definition = create_definition(client, auth)
    run = start_run(client, auth, definition, {"repo": "x"})
    assert client.post(f"/workflows/{run['id']}/retry", headers=auth).status_code == 400


def test_deleting_a_run_soft_deletes_its_tasks(client, auth, db):
    definition = create_definition(client, auth)
    run = start_run(client, auth, definition, {"repo": "x"})

    assert client.delete(f"/workflows/{run['id']}", headers=auth).status_code == 204
    assert client.get(f"/workflows/{run['id']}", headers=auth).status_code == 404
    db.expire_all()
    assert db.get(Task, step_task_id(run, "work")).deleted_at is not None


# --- schedules ----------------------------------------------------------------


def create_schedule(client, auth, definition, **overrides):
    body = {"name": "hourly", "cron_expression": "5 * * * *", "definition_id": definition["id"],
            "input": {"repo": "x"}, **overrides}
    return client.post("/schedules/", json=body, headers=auth)


def test_a_schedule_stores_validated_input_and_its_next_run(client, auth):
    definition = create_definition(client, auth)
    res = create_schedule(client, auth, definition)

    assert res.status_code == 201, res.text
    sched = res.json()
    assert sched["input"] == {"repo": "x", "hours": 24}
    assert sched["definition_name"] == "triage"
    assert datetime.fromisoformat(sched["next_run_at"]) > datetime.utcnow()
    assert [s["id"] for s in client.get("/schedules/", headers=auth).json()] == [sched["id"]]


def test_a_schedule_with_bad_cron_or_input_is_rejected(client, auth):
    definition = create_definition(client, auth)
    assert create_schedule(client, auth, definition, cron_expression="every hour").status_code == 422
    assert create_schedule(client, auth, definition, input={}).status_code == 422


def test_patching_cron_recomputes_the_next_run(client, auth):
    definition = create_definition(client, auth)
    sched = create_schedule(client, auth, definition).json()

    res = client.patch(f"/schedules/{sched['id']}", json={"cron_expression": "0 9 * * *"}, headers=auth)

    assert res.status_code == 200
    next_run = datetime.fromisoformat(res.json()["next_run_at"])
    assert next_run.hour == 1 and next_run.minute == 0  # 台北 09:00 = UTC 01:00


def test_patching_input_is_validated_against_the_definition(client, auth):
    definition = create_definition(client, auth)
    sched = create_schedule(client, auth, definition).json()

    bad = client.patch(f"/schedules/{sched['id']}", json={"input": {"hours": 3}}, headers=auth)
    assert bad.status_code == 422
    good = client.patch(f"/schedules/{sched['id']}", json={"input": {"repo": "y"}}, headers=auth)
    assert good.json()["input"] == {"repo": "y", "hours": 24}


def test_a_schedule_can_be_deleted(client, auth):
    definition = create_definition(client, auth)
    sched = create_schedule(client, auth, definition).json()

    assert client.delete(f"/schedules/{sched['id']}", headers=auth).status_code == 204
    assert client.get(f"/schedules/{sched['id']}", headers=auth).status_code == 404


def test_a_run_can_be_promoted_to_a_schedule_with_its_input(client, auth):
    definition = create_definition(client, auth)
    run = start_run(client, auth, definition, {"repo": "x"})

    res = client.post(
        f"/workflows/{run['id']}/promote-to-schedule",
        json={"name": "nightly", "cron_expression": "0 3 * * *"},
        headers=auth,
    )

    assert res.status_code == 201, res.text
    assert res.json()["definition_id"] == definition["id"]
    assert res.json()["input"] == run["input"]


def test_a_one_off_run_cannot_be_promoted(client, auth):
    run = client.post(
        "/workflows/",
        json={"name": "wf", "steps": [{"key": "a", "name": "a", "task_type": "echo"}]},
        headers=auth,
    ).json()

    res = client.post(
        f"/workflows/{run['id']}/promote-to-schedule",
        json={"name": "nightly", "cron_expression": "0 3 * * *"},
        headers=auth,
    )
    assert res.status_code == 400


def test_cron_is_read_in_taipei_time():
    # 台北 2026-10-25 08:00（UTC 00:00）之後的第一個「每天 9 點」是同一天台北 09:00 = UTC 01:00
    assert compute_next_run("0 9 * * *", datetime(2026, 10, 25, 0, 0)) == datetime(2026, 10, 25, 1, 0)
