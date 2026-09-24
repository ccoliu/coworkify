# ---------------------------------------------------
# Coworkify — executor integration tests (real DB, no Celery)
#
# These drive a workflow the way the workers do, minus the workers: create
# it with create_workflow_from_steps, then play each task's outcome through
# record_task_success / record_task_failure and assert what advance_workflow
# dispatched next and what it put in the payload. dispatch_task is replaced
# by a recorder, so no handler ever runs — task results are whatever the
# test says they are.
#
# The scenarios are the ones that broke in practice: inputs missing on a
# dispatch path, the 0-item reduce, orphaned reduce steps on failure/retry.
# ---------------------------------------------------

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.task import Task, TaskStatus
from app.models.workflow import Workflow, WorkflowStep, WorkFlowStatus
from app.tasks import executor
from app.tasks.executor import (
    create_workflow_from_steps,
    record_task_failure,
    record_task_success,
    retry_workflow_from_failure,
)

@pytest.fixture
def dispatched(monkeypatch):
    """每次 dispatch_task 派送的 task id，依派送順序。"""
    sent: list = []
    monkeypatch.setattr(executor, "dispatch_task", lambda task: sent.append(task.id))
    monkeypatch.setattr(executor, "notify_status_change", lambda *a, **kw: None)
    return sent

def step(key, task_type="echo", **extra):
    return {
        "key": key,
        "name": key,
        "task_type": task_type,
        "payload": extra.pop("payload", {}),
        "priority": 3,
        "max_retries": 0, # 失敗直接 failed
        **extra,
    }

def py(value):
    """python handler 的回傳形狀：使用者 main() 的回傳值在 value 裡。"""
    return {"stdout": "", "stderr": "", "exit_code": 0, "value": value}

class Run:
    """一條 workflow run 的操作介面：用 step key 找 task、模擬它成功或失敗。"""

    def __init__(self, db, workflow: Workflow):
        self.db = db
        self.workflow = workflow
    
    def task(self, key) -> Task:
        ws = self.db.scalars(
            select(WorkflowStep).where(
                WorkflowStep.workflow_id == self.workflow.id, WorkflowStep.step_key == key
            )
        ).one()
        return self.db.get(Task, ws.task_id)

    def expanded(self, template_name) -> list[Task]:
        """for_each 展開出來的 task（沒有 step_key），依項目順序。"""
        tasks = self.db.scalars(
            select(Task)
            .join(WorkflowStep, WorkflowStep.task_id == Task.id)
            .where(
                WorkflowStep.workflow_id == self.workflow.id,
                WorkflowStep.step_key.is_(None),
                Task.name.like(f"{template_name} [%]")
            )
        ).all()
        return sorted(tasks, key=lambda t: int(t.name.rsplit("[", 1)[1].rstrip("]")))
    
    # 測試 success task 流程
    def succeed(self, key_or_task, result):
        task = self.task(key_or_task) if isinstance(key_or_task, str) else key_or_task
        task.status = TaskStatus.RUNNING
        record_task_success(self.db, task, result)

    # 測試 failed task 流程
    def fail(self, key, error="boom"):
        task = self.task(key)
        task.status = TaskStatus.RUNNING
        assert record_task_failure(self.db, task, error) is None

    def status(self, key) -> str:
        task = self.task(key)
        self.db.refresh(task)
        return task.status

    def workflow_status(self) -> str:
        self.db.refresh(self.workflow)
        return self.workflow.status

def start(db, steps, **kwargs) -> Run:
    return Run(db, create_workflow_from_steps(db, "wf", steps, **kwargs))

# --- 線性流程 ---------------------------------------------------------------
def test_run_input_land_in_the_input_step_without_touching_the_template(db, dispatched):
    steps = [step("input_1", "input", payload={"data": {}})]
    run = start(db, steps, run_input={"repo": "apache/airflow"})

    assert run.task("input_1").payload["data"] == {"repo": "apache/airflow"}
    assert run.workflow.steps_template[0]["payload"] == {"data": {}}
    assert run.workflow.input == {"repo": "apache/airflow"}
    assert dispatched == [run.task("input_1").id]


def test_python_steps_get_every_ancestor_with_python_results_unwrapped(db, dispatched):
    run = start(db, [
        step("input_1", "input"),
        step("a", "python", depends_on=["input_1"]),
        step("b", "shell", depends_on=["a"]),
    ])

    run.succeed("input_1", {"repo": "x"})
    assert dispatched[-1] == run.task("a").id
    assert run.task("a").payload["inputs"] == {"input_1": {"repo": "x"}}

    run.succeed("a", py([1, 2]))
    # b 只直接依賴 a，但也拿得到更上游的 input_1；a 是 python，取的是 value
    assert run.task("b").payload["inputs"] == {"input_1": {"repo": "x"}, "a": [1, 2]}

    run.succeed("b", {"stdout": "ok"})
    assert run.workflow_status() == WorkFlowStatus.SUCCESS
    assert run.workflow.result == {"b": {"stdout": "ok"}}

def test_step_refs_are_rendered_before_dispatch(db, dispatched):
    run = start(db, [
        step("a"),
        step("b", payload={"url": "https://x/{{steps.a.result.id}}", "raw": "{{steps.a.result}}"}, depends_on=["a"])
    ])

    run.succeed("a", {"id": 7})
    assert run.task("b").payload == {"url": "https://x/7", "raw": {"id": 7}}

def test_a_step_waits_for_all_of_its_dependencies(db, dispatched):
    run = start(db, [step("a"), step("b"), step("c", depends_on=["a", "b"])])
    assert set(dispatched) == {run.task("a").id, run.task("b").id}

    run.succeed("a", {})
    assert run.task("c").id not in dispatched
    run.succeed("b", {})
    assert dispatched[-1] == run.task("c").id

# --- condition 分支 ---------------------------------------------------------

def test_condition_left_defaults_to_the_unwrapped_upstream_value(db, dispatched):
    run = start(db, [
        step("a", "python"),
        step("cond", "condition", payload={"operator": "is_true"}, depends_on=["a"]),
    ])

    run.succeed("a", py(True))
    assert run.task("cond").payload["left"] is True

def test_condition_cancels_the_losing_branch_and_its_downstream(db, dispatched):
    run = start(db, [
        step("cond", "condition"),
        step("yes", depends_on=["cond"], branch_of="cond", branch_when="true"),
        step("no", depends_on=["cond"], branch_of="cond", branch_when="false"),
        step("after_no", depends_on=["no"]),
    ])

    run.succeed("cond", {"passed": True})
    assert run.status("no") == TaskStatus.CANCELLED
    assert run.status("after_no") == TaskStatus.CANCELLED
    assert dispatched[-1] == run.task("yes").id

    run.succeed("yes", {})
    assert run.workflow_status() == WorkFlowStatus.SUCCESS

# --- for_each / reduce ------------------------------------------------------

def _fan_out_steps():
    return [
        step("input_1", "input"),
        step("src", "python", depends_on=["input_1"]),
        step("judge", payload={"issue": "{{item}}"}, for_each="src"),
        step("digest", "python", reduce_of="judge"),
        step("notify", depends_on=["digest"]),
    ]

def test_for_each_expands_one_task_per_item(db, dispatched):
    run = start(db, _fan_out_steps())
    run.succeed("input_1", {"repo": "x"})
    run.succeed("src", py(["a", "b", "c"]))

    judges = run.expanded("judge")
    assert [t.payload["issue"] for t in judges] == ["a", "b", "c"]
    assert dispatched[-3:] == [t.id for t in judges]

def test_reduce_waits_for_every_item_and_gets_results_in_item_order(db, dispatched):
    run = start(db, _fan_out_steps())
    run.succeed("input_1", {"repo": "x"})
    run.succeed("src", py(["a", "b", "c"]))
    a, b, c = run.expanded("judge")

    # 故意亂序完成：reduce 拿到的 list 仍要對齊 src 的項目順序
    run.succeed(c, {"verdict": "c"})
    run.succeed(a, {"verdict": "a"})
    assert run.task("digest").id not in dispatched
    run.succeed(b, {"verdict": "b"})

    assert dispatched[-1] == run.task("digest").id
    assert run.task("digest").payload["inputs"] == {
        "input_1": {"repo": "x"},
        "src": ["a", "b", "c"],
        "judge": [
            {"verdict": "a"},
            {"verdict": "b"},
            {"verdict": "c"},
        ]
    }

    run.succeed("digest", py({"has_news": True}))
    run.succeed("notify", {})
    assert run.workflow_status() == WorkFlowStatus.SUCCESS

def test_zero_items_still_dispatches_the_reduce_with_full_inputs(db, dispatched):
    run = start(db, _fan_out_steps())
    run.succeed("input_1", {"repo": "x"})
    run.succeed("src", py([]))

    assert run.expanded("judge") == []
    assert dispatched[-1] == run.task("digest").id
    # depends_on 是空的，inputs 得從 for_each 來源往上找，input_1 不能掉
    assert run.task("digest").payload["inputs"] == {
        "input_1": {"repo": "x"},
        "src": [],
        "judge": []
    }

    run.succeed("digest", py({"has_news": False}))
    assert dispatched[-1] == run.task("notify").id
    run.succeed("notify", {})
    assert run.workflow_status() == WorkFlowStatus.SUCCESS

def test_a_non_list_source_expands_to_zero_items(db, dispatched):
    run = start(db, _fan_out_steps())
    run.succeed("input_1", {})
    run.succeed("src", py({"not": "a list"}))

    assert run.expanded("judge") == []
    assert run.task("digest").payload["inputs"]["judge"] == []

# --- 失敗與續跑 --------------------------------------------------------------

def test_failure_cancels_downstream_and_marks_the_workflow_failed(db, dispatched):
    run = start(db, [step("a"), step("b", depends_on=["a"]), step("c", depends_on=["b"])])
    run.succeed("a", {})
    run.fail("b")

    assert run.status("c") == TaskStatus.CANCELLED
    assert run.workflow_status() == WorkFlowStatus.FAILED


def test_retry_resumes_from_the_failed_steps(db, dispatched):
    run = start(db, [step("a"), step("b", depends_on=["a"]), step("c", depends_on=["b"])])
    run.succeed("a", {})
    run.fail("b")
    dispatched.clear()

    assert retry_workflow_from_failure(db, run.workflow) == 2
    assert run.status("a") == TaskStatus.SUCCESS
    assert run.status("b") == TaskStatus.PENDING
    assert run.status("c") == TaskStatus.PENDING
    assert dispatched == [run.task("b").id]

    run.succeed("b", {})
    run.succeed("c", {})
    assert run.workflow_status() == WorkFlowStatus.SUCCESS

def test_failure_before_expansion_cancels_the_orphan_reduce_and_retry_revives_it(db, dispatched):
    run = start(db, _fan_out_steps())
    run.succeed("input_1", {"repo": "x"})
    run.fail("src")

    # digest 的 depends_on 還是空的，一般的下游走訪走不到它
    assert run.status("notify") == TaskStatus.CANCELLED
    assert run.status("digest") == TaskStatus.CANCELLED
    assert run.workflow_status() == WorkFlowStatus.FAILED

    assert retry_workflow_from_failure(db, run.workflow) == 3
    assert run.status("digest") == TaskStatus.PENDING
    assert run.status("notify") == TaskStatus.PENDING

    run.succeed("src", py(["a"]))
    (only,) = run.expanded("judge")
    run.succeed(only, {"verdict": "a"})
    assert run.task("digest").payload["inputs"]["judge"] == [{"verdict": "a"}]
    run.succeed("digest", py({}))
    run.succeed("notify", {})
    assert run.workflow_status() == WorkFlowStatus.SUCCESS

def test_retry_does_not_revive_a_branch_that_lost(db, dispatched):
    run = start(db, [
        step("cond", "condition"),
        step("yes", depends_on=["cond"], branch_of="cond", branch_when="true"),
        step("no", depends_on=["cond"], branch_of="cond", branch_when="false"),
        step("join", depends_on=["yes"]),
    ])
    run.succeed("cond", {"passed": True})
    run.fail("yes")

    retry_workflow_from_failure(db, run.workflow)
    assert run.status("yes") == TaskStatus.PENDING
    assert run.status("join") == TaskStatus.PENDING
    assert run.status("no") == TaskStatus.CANCELLED