# ---------------------------------------------------
# Coworkify — workflow-completion triggers (issue #9, phase 2)
#
# What has to hold:
#   - when a run of the source definition ends, advance_workflow enqueues
#     coworkify.fire_workflow_triggers, but only if a trigger is waiting for
#     that definition and that outcome (success / failed / any);
#   - firing starts the target with input mapped from the source run's
#     result / input, and the same source run + outcome fires only once;
#   - a bad target input lands on the trigger as last_error, never on the
#     source run;
#   - loops are rejected when a trigger is created, and chains are capped at
#     run time as a backstop;
#   - workflow triggers have no secret and can't be called from outside.
# ---------------------------------------------------

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.models.task import Task, TaskStatus
from app.models.trigger import WorkflowTrigger
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep
from app.tasks import executor, triggers
from app.tasks.executor import create_workflow_from_steps, record_task_failure, record_task_success
from app.tasks.triggers import MAX_CHAIN_DEPTH, run_workflow_triggers

SOURCE_STEPS = [
    {"key": "input_1", "name": "input", "task_type": "input", "payload": {}, "priority": 3},
    {
        "key": "summarize", "name": "summarize", "task_type": "echo", "payload": {}, "priority": 3,
        "max_retries": 0, "depends_on": ["input_1"],
    },
]
TARGET_STEPS = [{"key": "input_1", "name": "input", "task_type": "input", "payload": {}, "priority": 3}]
TARGET_SCHEMA = [
    {"key": "summary", "label": "Summary", "kind": "string", "required": True},
    {"key": "repo", "label": "Repository", "kind": "string", "required": False},
]


@pytest.fixture(autouse=True)
def connections_key(monkeypatch):
    monkeypatch.setenv("CONNECTIONS_KEY", Fernet.generate_key().decode())


@pytest.fixture
def enqueued(monkeypatch):
    """advance_workflow 派出去的 fire_workflow_triggers，(source_id, status)。"""
    sent: list = []
    monkeypatch.setattr(
        executor.celery_app, "send_task", lambda name, args=None, **kw: sent.append((name, *args))
    )
    return sent


def make_definition(client, auth, name, steps, schema=None) -> str:
    res = client.post("/definitions/", json={"name": name, "steps": steps, "input_schema": schema or []}, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture
def source_id(client, auth):
    return make_definition(client, auth, "summarize issues", SOURCE_STEPS, [{"key": "repo", "label": "Repo", "kind": "string"}])


@pytest.fixture
def target_id(client, auth):
    return make_definition(client, auth, "post summary", TARGET_STEPS, TARGET_SCHEMA)


def create_trigger(client, auth, source, target, **extra):
    body = {
        "name": "after summary",
        "kind": "workflow",
        "source_definition_id": source,
        "definition_id": target,
        "input_mapping": {"summary": "result.summarize.text", "repo": "input.repo"},
        **extra,
    }
    return client.post("/triggers/", json=body, headers=auth)


@pytest.fixture
def trigger(client, auth, source_id, target_id):
    res = create_trigger(client, auth, source_id, target_id)
    assert res.status_code == 201, res.text
    return res.json()


def owner(db, username="alice") -> User:
    return db.scalars(select(User).where(User.username == username)).one()


def source_run(db, source_id, *, created_by=None) -> Workflow:
    return create_workflow_from_steps(
        db, "summarize issues", SOURCE_STEPS, definition_id=source_id,
        run_input={"repo": "ccoliu/coworkify"}, created_by=created_by or owner(db).id,
    )


def task_of(db, run, key) -> Task:
    ws = db.scalars(
        select(WorkflowStep).where(WorkflowStep.workflow_id == run.id, WorkflowStep.step_key == key)
    ).one()
    return db.get(Task, ws.task_id)


def finish(db, run, result=None, *, fail=False):
    """input 成功，summarize 以 result 成功（或失敗），整條 run 就結束了。"""
    first = task_of(db, run, "input_1")
    first.status = TaskStatus.RUNNING
    record_task_success(db, first, run.input)
    task = task_of(db, run, "summarize")
    task.status = TaskStatus.RUNNING
    if fail:
        record_task_failure(db, task, "boom")
    else:
        record_task_success(db, task, result)


def runs_of(db, definition_id) -> list[Workflow]:
    db.expire_all()
    return db.scalars(select(Workflow).where(Workflow.definition_id == definition_id)).all()


def reload_trigger(db, trigger) -> WorkflowTrigger:
    db.expire_all()
    return db.get(WorkflowTrigger, trigger["id"])


# --- managing ----------------------------------------------------------------------


def test_a_workflow_trigger_has_no_secret_or_hook(trigger):
    assert trigger["kind"] == "workflow"
    assert trigger["on_status"] == "success"
    assert trigger["secret"] is None
    assert trigger["hook_path"] is None


def test_a_workflow_trigger_needs_a_source(client, auth, target_id):
    res = client.post(
        "/triggers/", json={"name": "x", "kind": "workflow", "definition_id": target_id}, headers=auth
    )
    assert res.status_code == 422


def test_triggering_itself_is_rejected(client, auth, source_id):
    res = create_trigger(client, auth, source_id, source_id, input_mapping={})
    assert res.status_code == 400
    assert "loop" in res.json()["detail"]


def test_a_longer_loop_is_rejected(client, auth):
    a = make_definition(client, auth, "a", SOURCE_STEPS)
    b = make_definition(client, auth, "b", SOURCE_STEPS)
    c = make_definition(client, auth, "c", SOURCE_STEPS)
    assert create_trigger(client, auth, a, b, input_mapping={}).status_code == 201
    assert create_trigger(client, auth, b, c, input_mapping={}).status_code == 201

    back_to_start = create_trigger(client, auth, c, a, input_mapping={})
    assert back_to_start.status_code == 400
    # 同一個方向多一條捷徑不是循環
    assert create_trigger(client, auth, a, c, input_mapping={}).status_code == 201


def test_someone_elses_source_is_off_limits(client, auth, other_auth, target_id):
    theirs = make_definition(client, other_auth, "theirs", SOURCE_STEPS)
    assert create_trigger(client, auth, theirs, target_id).status_code == 400


def test_it_has_no_secret_to_rotate_and_no_url_to_call(client, auth, trigger):
    assert client.post(f"/triggers/{trigger['id']}/rotate-secret", headers=auth).status_code == 400
    assert client.post(f"/hooks/{trigger['id']}", json={}).status_code == 404


def test_on_status_can_be_changed_but_only_on_workflow_triggers(client, auth, trigger, target_id):
    res = client.patch(f"/triggers/{trigger['id']}", json={"on_status": "any"}, headers=auth)
    assert res.json()["on_status"] == "any"

    webhook = client.post("/triggers/", json={"name": "hook", "definition_id": target_id}, headers=auth).json()
    assert client.patch(f"/triggers/{webhook['id']}", json={"on_status": "any"}, headers=auth).status_code == 400


# --- enqueueing from advance_workflow -----------------------------------------------


def test_a_finished_run_enqueues_the_triggers_waiting_for_it(client, trigger, source_id, enqueued, db):
    run = source_run(db, source_id)
    finish(db, run, {"text": "two bugs"})

    assert enqueued == [("coworkify.fire_workflow_triggers", str(run.id), "success")]


def test_nothing_is_enqueued_when_no_one_is_waiting(client, auth, source_id, enqueued, db):
    run = source_run(db, source_id)
    finish(db, run, {"text": "two bugs"})
    assert enqueued == []


def test_the_outcome_has_to_match(client, auth, trigger, source_id, enqueued, db):
    failed = source_run(db, source_id)
    finish(db, failed, fail=True)
    assert enqueued == [], "the trigger waits for success, not failure"

    client.patch(f"/triggers/{trigger['id']}", json={"on_status": "any"}, headers=auth)
    failed_again = source_run(db, source_id)
    finish(db, failed_again, fail=True)
    assert enqueued == [("coworkify.fire_workflow_triggers", str(failed_again.id), "failed")]


def test_a_disabled_trigger_is_not_waited_on(client, auth, trigger, source_id, enqueued, db):
    client.patch(f"/triggers/{trigger['id']}", json={"enabled": False}, headers=auth)
    finish(db, source_run(db, source_id), {"text": "x"})
    assert enqueued == []


# --- firing -----------------------------------------------------------------------


def test_firing_starts_the_target_with_input_from_the_source_run(client, trigger, source_id, target_id, enqueued, db):
    run = source_run(db, source_id)
    finish(db, run, {"text": "two bugs"})

    assert run_workflow_triggers(db, run.id, "success") == 1

    [started] = runs_of(db, target_id)
    assert started.input == {"summary": "two bugs", "repo": "ccoliu/coworkify"}
    assert started.trigger_kind == "workflow"
    assert str(started.trigger_id) == trigger["id"]
    assert started.trigger_delivery_id == f"{run.id}:success"
    assert started.created_by == owner(db).id
    assert reload_trigger(db, trigger).last_triggered_at is not None


def test_the_detail_page_links_the_upstream_and_downstream_runs(client, auth, trigger, source_id, target_id, enqueued, db):
    run = source_run(db, source_id)
    finish(db, run, {"text": "two bugs"})
    run_workflow_triggers(db, run.id, "success")
    [started] = runs_of(db, target_id)

    downstream = client.get(f"/workflows/{started.id}", headers=auth).json()
    assert downstream["upstream_run"]["id"] == str(run.id)
    assert downstream["upstream_run"]["status"] == "success"
    assert downstream["upstream_run"]["via_status"] == "success"
    assert downstream["downstream_runs"] == []

    upstream = client.get(f"/workflows/{run.id}", headers=auth).json()
    assert upstream["upstream_run"] is None
    assert [r["id"] for r in upstream["downstream_runs"]] == [str(started.id)]
    assert upstream["downstream_runs"][0]["name"] == "post summary"
    assert upstream["downstream_runs"][0]["via_status"] == "success"


def test_the_same_run_and_outcome_fire_once(client, trigger, source_id, target_id, enqueued, db):
    run = source_run(db, source_id)
    finish(db, run, {"text": "two bugs"})

    assert run_workflow_triggers(db, run.id, "success") == 1
    assert run_workflow_triggers(db, run.id, "success") == 0
    assert len(runs_of(db, target_id)) == 1


def test_a_retried_run_that_succeeds_fires_the_success_side(client, auth, trigger, source_id, target_id, enqueued, db):
    client.patch(f"/triggers/{trigger['id']}", json={"on_status": "any", "input_mapping": {"summary": "status"}}, headers=auth)
    run = source_run(db, source_id)

    assert run_workflow_triggers(db, run.id, "failed") == 1
    assert run_workflow_triggers(db, run.id, "success") == 1
    assert sorted(w.input["summary"] for w in runs_of(db, target_id)) == ["failed", "success"]


def test_the_filter_applies_to_the_source_run(client, auth, trigger, source_id, target_id, enqueued, db):
    client.patch(f"/triggers/{trigger['id']}", json={"filter": {"result.summarize.severity": "high"}}, headers=auth)

    low = source_run(db, source_id)
    finish(db, low, {"text": "typo", "severity": "low"})
    high = source_run(db, source_id)
    finish(db, high, {"text": "data loss", "severity": "high"})

    assert run_workflow_triggers(db, low.id, "success") == 0
    assert run_workflow_triggers(db, high.id, "success") == 1
    assert [w.input["summary"] for w in runs_of(db, target_id)] == ["data loss"]


def test_bad_input_is_kept_on_the_trigger_not_the_source(client, trigger, source_id, target_id, enqueued, db):
    run = source_run(db, source_id)
    finish(db, run, {"no_text_here": True})

    assert run_workflow_triggers(db, run.id, "success") == 0

    assert runs_of(db, target_id) == []
    assert "Summary" in reload_trigger(db, trigger).last_error
    db.refresh(run)
    assert run.status == "success"


def test_someone_elses_run_does_not_fire_my_trigger(client, trigger, source_id, target_id, other_auth, enqueued, db):
    run = source_run(db, source_id, created_by=owner(db, "mallory").id)
    finish(db, run, {"text": "x"})

    assert run_workflow_triggers(db, run.id, "success") == 0
    assert runs_of(db, target_id) == []


def test_a_chain_that_is_too_deep_stops(client, trigger, source_id, target_id, enqueued, db):
    # 做出一條已經有 MAX_CHAIN_DEPTH 層的 workflow 觸發鏈，最後一個是 source 的 run
    parent = source_run(db, source_id)
    for _ in range(MAX_CHAIN_DEPTH):
        parent = create_workflow_from_steps(
            db, "link", SOURCE_STEPS, definition_id=source_id, run_input={"repo": "r"}, created_by=owner(db).id,
            trigger_kind="workflow", trigger_id=trigger["id"], trigger_delivery_id=f"{parent.id}:success",
        )
    finish(db, parent, {"text": "x"})

    assert run_workflow_triggers(db, parent.id, "success") == 0
    assert "ChainTooDeep" in reload_trigger(db, trigger).last_error


def test_the_celery_task_is_registered_under_the_enqueued_name():
    assert triggers.fire_workflow_triggers.name == "coworkify.fire_workflow_triggers"
