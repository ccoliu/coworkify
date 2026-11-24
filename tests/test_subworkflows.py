# ---------------------------------------------------
# Coworkify — sub-workflows (issue #10)
#
# A subworkflow step runs another definition as a child run and waits for
# it without holding a worker (it is a sensor, like wait_for). What has to hold:
#   - the child gets its input from the step's payload and records who called it;
#   - the step waits, and a second check or a crashed attempt doesn't start a
#     second child;
#   - when the child ends it wakes the step, which succeeds with the child's
#     result or fails naming the child and the step that broke;
#   - a retry starts a fresh child; a missing definition fails without retrying;
#   - loops are rejected on save and nesting is capped at run time.
#
# execute_task is called directly with SessionLocal pointed at the test database.
# ---------------------------------------------------

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.task import Task, TaskStatus
from app.models.user import User
from app.models.workflow import Workflow, WorkflowDefinition, WorkflowStep, WorkFlowStatus
from app.tasks import executor, subworkflow
from app.tasks.executor import execute_task
from app.tasks.handler import PermanentTaskError
from app.tasks.triggers import _chain_depth

CHILD_SCHEMA = [{"key": "repo", "label": "Repo", "kind": "string", "required": True}]
CHILD_STEPS = [
    {"key": "input_1", "name": "input", "task_type": "input", "payload": {}, "priority": 3},
    {
        "key": "summarize", "name": "summarize", "task_type": "echo", "priority": 3,
        "payload": {"message": "summary of {{steps.input_1.result.repo}}"}, "depends_on": ["input_1"],
    },
]
FAILING_CHILD_STEPS = [
    {
        "key": "explode", "name": "explode", "task_type": "flaky_task", "priority": 3,
        "payload": {"should_fail": True}, "max_retries": 0,
    },
]


def call_step(definition_id, **extra):
    return {
        "key": "call", "name": "call child", "task_type": "subworkflow", "priority": 3,
        "payload": {"definition_id": definition_id, "repo": "ccoliu/coworkify"}, **extra,
    }


AFTER = {"key": "after", "name": "after", "task_type": "echo", "payload": {}, "priority": 3, "depends_on": ["call"]}


@pytest.fixture
def worker_db(db_engine, monkeypatch):
    monkeypatch.setattr(executor, "SessionLocal", sessionmaker(bind=db_engine, autoflush=False))


def make_definition(client, auth, name, steps, schema=None) -> str:
    res = client.post("/definitions/", json={"name": name, "steps": steps, "input_schema": schema or []}, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def start_run(client, auth, definition_id) -> str:
    res = client.post(f"/definitions/{definition_id}/runs", json={}, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def task_of(db, run_id, key) -> Task:
    db.expire_all()
    task_id = db.scalars(
        select(WorkflowStep.task_id).where(WorkflowStep.workflow_id == uuid.UUID(str(run_id)), WorkflowStep.step_key == key)
    ).one()
    return db.get(Task, task_id)


def children(db, task) -> list[Workflow]:
    db.expire_all()
    return subworkflow.child_runs(db, task.id)


def run_child_to_the_end(db, child: Workflow):
    for key in ("input_1", "summarize"):
        execute_task(str(task_of(db, child.id, key).id))


@pytest.fixture
def child_id(client, auth):
    return make_definition(client, auth, "summarize repo", CHILD_STEPS, CHILD_SCHEMA)


@pytest.fixture
def parent_id(client, auth, child_id):
    return make_definition(client, auth, "nightly", [call_step(child_id), AFTER])


@pytest.fixture
def started(client, auth, parent_id, worker_db, db):
    """父 run 的 subworkflow 步驟跑過第一次：子 run 建好了，步驟在 WAITING。"""
    run_id = start_run(client, auth, parent_id)
    step = task_of(db, run_id, "call")
    execute_task(str(step.id))
    return run_id, step


# --- running -------------------------------------------------------------------------


def test_the_step_starts_a_child_run_and_waits(client, started, child_id, db):
    run_id, step = started
    [child] = children(db, step)

    assert child.definition_id == uuid.UUID(child_id)
    assert child.trigger_kind == "subworkflow"
    assert child.trigger_id == step.id
    assert child.input == {"repo": "ccoliu/coworkify"}
    assert child.created_by == db.get(Workflow, uuid.UUID(run_id)).created_by

    step = task_of(db, run_id, "call")
    assert step.status == TaskStatus.WAITING
    assert step.retry_count == 0


def test_a_check_while_the_child_runs_does_not_start_another(started, db):
    run_id, step = started
    step = task_of(db, run_id, "call")
    step.scheduled_at = step.scheduled_at.replace(year=2000)  # 備援檢查到期
    db.commit()

    execute_task(str(step.id))

    assert len(children(db, step)) == 1
    assert task_of(db, run_id, "call").status == TaskStatus.WAITING


def test_a_crash_after_starting_the_child_reuses_it(client, auth, parent_id, worker_db, db):
    run_id = start_run(client, auth, parent_id)
    step = task_of(db, run_id, "call")
    execute_task(str(step.id))
    # worker 在轉成 WAITING 之前掛掉，recover_stale_running_tasks 把它排回 RETRYING
    step = task_of(db, run_id, "call")
    step.status = TaskStatus.RETRYING
    db.commit()

    execute_task(str(step.id))

    assert len(children(db, step)) == 1
    assert task_of(db, run_id, "call").status == TaskStatus.WAITING


def test_the_child_finishing_wakes_the_step_and_its_result_flows_downstream(client, started, db):
    run_id, step = started
    [child] = children(db, step)
    client.dispatched.clear()

    run_child_to_the_end(db, child)

    db.expire_all()
    assert db.get(Workflow, child.id).status == WorkFlowStatus.SUCCESS
    assert step.id in client.dispatched  # 被叫醒了，不用等備援檢查

    execute_task(str(step.id))

    step = task_of(db, run_id, "call")
    assert step.status == TaskStatus.SUCCESS
    result = executor.collect_step_results(db, [str(step.id)])[0]
    assert result["summarize"]["message"] == "summary of ccoliu/coworkify"
    assert task_of(db, run_id, "after").id in client.dispatched


def test_a_failed_child_fails_the_step_naming_the_child_and_the_step(client, auth, worker_db, db):
    failing = make_definition(client, auth, "breaks", FAILING_CHILD_STEPS)
    parent = make_definition(client, auth, "nightly", [call_step(failing) | {"payload": {"definition_id": failing}}, AFTER])
    run_id = start_run(client, auth, parent)
    step = task_of(db, run_id, "call")
    execute_task(str(step.id))
    [child] = children(db, step)

    with pytest.raises(RuntimeError):
        execute_task(str(task_of(db, child.id, "explode").id))
    with pytest.raises(RuntimeError, match=rf"Child run {child.id} \(breaks\) failed at step 'explode'"):
        execute_task(str(step.id))

    db.expire_all()
    assert task_of(db, run_id, "call").status == TaskStatus.FAILED
    assert task_of(db, run_id, "after").status == TaskStatus.CANCELLED
    assert db.get(Workflow, uuid.UUID(run_id)).status == WorkFlowStatus.FAILED


def test_a_retry_starts_a_new_child_and_keeps_the_old_one(client, auth, worker_db, db):
    failing = make_definition(client, auth, "breaks", FAILING_CHILD_STEPS)
    parent = make_definition(
        client, auth, "nightly", [call_step(failing) | {"payload": {"definition_id": failing}, "max_retries": 1}]
    )
    run_id = start_run(client, auth, parent)
    step = task_of(db, run_id, "call")
    execute_task(str(step.id))
    [first] = children(db, step)
    with pytest.raises(RuntimeError):
        execute_task(str(task_of(db, first.id, "explode").id))

    # 直接呼叫 task 時 self.retry 會把原本的例外丟回來，不是 Retry
    with pytest.raises(RuntimeError):
        execute_task(str(step.id))
    assert task_of(db, run_id, "call").status == TaskStatus.RETRYING

    execute_task(str(step.id))

    newest, oldest = children(db, step)
    assert oldest.id == first.id and newest.id != first.id
    assert task_of(db, run_id, "call").status == TaskStatus.WAITING


def test_subworkflow_steps_do_not_retry_unless_asked(client, auth, child_id):
    parent = make_definition(client, auth, "nightly", [call_step(child_id)])
    res = client.get(f"/definitions/{parent}", headers=auth)
    assert res.json()["steps"][0]["max_retries"] == 0


def test_a_definition_that_is_gone_fails_without_retrying(client, auth, child_id, worker_db, db):
    parent = make_definition(client, auth, "nightly", [call_step(child_id, max_retries=3)])
    run_id = start_run(client, auth, parent)
    db.delete(db.get(WorkflowDefinition, uuid.UUID(child_id)))
    db.commit()

    with pytest.raises(PermanentTaskError, match="no longer exists"):
        execute_task(str(task_of(db, run_id, "call").id))

    step = task_of(db, run_id, "call")
    assert step.status == TaskStatus.FAILED
    assert children(db, step) == []


def test_input_the_child_rejects_fails_without_retrying(client, auth, child_id, worker_db, db):
    parent = make_definition(
        client, auth, "nightly", [call_step(child_id, max_retries=3) | {"payload": {"definition_id": child_id}}]
    )
    run_id = start_run(client, auth, parent)

    with pytest.raises(PermanentTaskError, match="Repo"):
        execute_task(str(task_of(db, run_id, "call").id))
    assert task_of(db, run_id, "call").status == TaskStatus.FAILED


def test_nesting_is_capped(client, auth, child_id, worker_db, db, monkeypatch):
    monkeypatch.setattr(subworkflow, "MAX_DEPTH", 1)
    middle = make_definition(client, auth, "middle", [call_step(child_id)])
    top = make_definition(client, auth, "top", [call_step(middle) | {"payload": {"definition_id": middle}}])
    run_id = start_run(client, auth, top)
    top_step = task_of(db, run_id, "call")
    execute_task(str(top_step.id))
    [middle_run] = children(db, top_step)

    with pytest.raises(PermanentTaskError, match="nest 1 levels"):
        execute_task(str(task_of(db, middle_run.id, "call").id))


def test_someone_elses_definition_cannot_be_run(client, auth, other_auth, child_id, worker_db, db):
    parent = make_definition(client, auth, "nightly", [call_step(child_id)])
    run_id = start_run(client, auth, parent)
    # 定義換了主人（例如帳號合併出錯）：當成不存在
    definition = db.get(WorkflowDefinition, uuid.UUID(child_id))
    definition.created_by = db.scalars(select(User.id).where(User.username == "mallory")).one()
    db.commit()

    with pytest.raises(PermanentTaskError, match="no longer exists"):
        execute_task(str(task_of(db, run_id, "call").id))


def test_a_child_run_counts_toward_the_trigger_chain_depth(started, db):
    _, step = started
    [child] = children(db, step)
    assert _chain_depth(db, child) == 1


# --- saving --------------------------------------------------------------------------


def test_the_called_workflow_has_to_exist_and_be_yours(client, auth, other_auth, child_id):
    res = client.post("/definitions/", json={"name": "x", "steps": [call_step(str(uuid.uuid4()))]}, headers=auth)
    assert res.status_code == 400 and "not found" in res.json()["detail"]

    res = client.post("/definitions/", json={"name": "x", "steps": [call_step(child_id)]}, headers=other_auth)
    assert res.status_code == 400

    res = client.post("/definitions/", json={"name": "x", "steps": [call_step("not-an-id")]}, headers=auth)
    assert res.status_code == 400 and "valid UUID" in res.json()["detail"]


def test_inputs_the_child_does_not_declare_are_rejected(client, auth, child_id):
    step = call_step(child_id)
    step["payload"]["branch"] = "main"
    res = client.post("/definitions/", json={"name": "x", "steps": [step]}, headers=auth)
    assert res.status_code == 400 and "branch" in res.json()["detail"]


def test_calling_itself_is_rejected(client, auth, parent_id, child_id):
    body = {"name": "nightly", "steps": [call_step(parent_id)]}
    res = client.put(f"/definitions/{parent_id}", json=body, headers=auth)
    assert res.status_code == 400 and "loop" in res.json()["detail"]


def test_a_longer_loop_is_rejected(client, auth, parent_id, child_id):
    # nightly 呼叫 summarize repo；把 summarize repo 改成呼叫 nightly 就成環了
    body = {"name": "summarize repo", "steps": [call_step(parent_id) | {"payload": {"definition_id": parent_id}}]}
    res = client.put(f"/definitions/{child_id}", json=body, headers=auth)
    assert res.status_code == 400 and "loop" in res.json()["detail"]


# --- reading -------------------------------------------------------------------------


def test_the_step_links_to_its_child_and_the_child_back_to_the_step(client, auth, started, db):
    run_id, step = started
    [child] = children(db, step)

    parent = client.get(f"/workflows/{run_id}", headers=auth).json()
    call = next(s for s in parent["steps"] if s["step_key"] == "call")
    assert call["child_workflow_id"] == str(child.id)

    detail = client.get(f"/workflows/{child.id}", headers=auth).json()
    assert detail["parent_run"]["id"] == run_id
    assert detail["parent_step_name"] == "call child"
    assert detail["trigger_kind"] == "subworkflow"
