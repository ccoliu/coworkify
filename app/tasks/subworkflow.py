"""
subworkflow 步驟：把另一條 workflow 定義當成一個步驟來跑，等它結束，把它的成品交給下游（issue #10）。

payload 是 {"definition_id": "<要呼叫的定義>", <那個定義的 input_schema 欄位>...}。

執行方式跟 wait_for 一樣是 sensor，等待期間不佔 worker：
1. 第一次執行：建一個子 run（trigger_kind = "subworkflow"、trigger_id = 這個步驟的 task id），
   丟 NotReady，步驟轉成 WAITING，排一個備援檢查。
2. 子 run 結束時，advance_workflow 把這個步驟的 scheduled_at 拉到現在並派送（wake_parent_step），
   步驟被認領、看到子 run 結束了：成功就以子 run 的 result 成功，失敗就失敗。
3. 喚醒的訊息遺失時，由備援檢查或 recover_lost_waiting_tasks 接手。

子 run 的 trigger_id 存的是 task id，不是排程或觸發器：workflows.trigger_id 刻意沒有 FK，
(trigger_id, trigger_delivery_id) 的 unique constraint 也剛好讓「用 task id 找子 run」吃得到 index。
"""

import uuid

from sqlalchemy import select

from app.models.task import Task, TaskStatus
from app.models.workflow import Workflow, WorkflowDefinition, WorkflowStep, WorkFlowStatus
from app.schemas.definition import resolve_run_input
from app.tasks.executor import create_workflow_from_steps
from app.tasks.handler import NotReady, PermanentTaskError



SUBWORKFLOW = "subworkflow"
# 子 run 裡還能再呼叫子 run，最多幾層（A 呼叫 B 呼叫 C 是兩層）
MAX_DEPTH = 5
# 正常是子 run 結束時被叫醒；這是喚醒訊息遺失時的備援檢查間隔
FALLBACK_CHECK_SECONDS = 60
# payload 裡不是子 run 輸入的欄位
_RESERVED_KEYS = {"definition_id"}


def child_runs(db, task_id) -> list[Workflow]:
    """這個 subworkflow 步驟建過的所有子 run，新的在前。重試一次就多一個，舊的留著看得到。"""
    return db.scalars(
        select(Workflow)
        .where(Workflow.trigger_kind == SUBWORKFLOW, Workflow.trigger_id == task_id)
        .order_by(Workflow.created_at.desc())
    ).all()


def parent_run_of_task(db, task_id) -> Workflow | None:
    step = db.scalars(select(WorkflowStep).where(WorkflowStep.task_id == task_id)).first()
    return db.get(Workflow, step.workflow_id) if step else None


def parent_run(db, run: Workflow) -> Workflow | None:
    """run 若是某個 subworkflow 步驟建出來的子 run，回傳那個步驟所在的 run。"""
    if run.trigger_kind != SUBWORKFLOW or run.trigger_id is None:
        return None
    return parent_run_of_task(db, run.trigger_id)


def nesting_depth(db, run: Workflow) -> int:
    """run 外面包了幾層 subworkflow（直接手動跑的是 0）。"""
    depth = 0
    current = parent_run(db, run)
    while current is not None and depth <= MAX_DEPTH:
        depth += 1
        current = parent_run(db, current)
    return depth


def child_input(payload: dict) -> dict:
    """payload 裡屬於子 run 輸入的部分：拿掉 definition_id 和執行器自己塞的 _ 開頭欄位。"""
    return {k:v for k, v in payload.items() if k not in _RESERVED_KEYS and not k.startswith("_")}


def _failure_message(db, child: Workflow) -> str:
    failed = db.scalars(
        select(Task)
        .join(WorkflowStep, WorkflowStep.task_id == Task.id)
        .where(WorkflowStep.workflow_id == child.id, Task.status == TaskStatus.FAILED)
    ).all()
    where = f" at step {', '.join(repr(t.name) for t in failed)}" if failed else ""
    return f"Child run {child.id} ({child.name}) failed{where}"


def _start_child(db, task: Task, payload: dict) -> Workflow:
    parent = parent_run_of_task(db, task.id)
    owner = parent.created_by if parent is not None else task.created_by

    
    try:
        definition_id = uuid.UUID(str(payload.get("definition_id")))
    except ValueError:
        raise PermanentTaskError("payload.definition_id must be a workflow definition id") from None
    definition = db.get(WorkflowDefinition, definition_id)
    # 別人的定義跟不存在一樣
    if definition is None or definition.created_by != owner:
        raise PermanentTaskError(f"Workflow definition {definition_id} no longer exists")

    if parent is not None and nesting_depth(db, parent) + 1 > MAX_DEPTH:
        raise PermanentTaskError(f"Sub-workflows can only nest {MAX_DEPTH} levels deep")

    try:
        run_input = resolve_run_input(definition.input_schema, child_input(payload)) if definition.input_schema else None
    except ValueError as exc:
        raise PermanentTaskError(f"Input for '{definition.name}' is invalid: {exc}") from None

    return create_workflow_from_steps(
        db,
        definition.name,
        definition.steps,
        definition_id=definition.id,
        definition_version=definition.version,
        run_input=run_input,
        created_by=owner,
        trigger_kind=SUBWORKFLOW,
        trigger_id=task.id,
    )


def run_subworkflow_step(db, task: Task, payload: dict, *, resumed: bool):
    """
    執行一次 subworkflow 步驟。子 run 還沒結束就丟 NotReady；結束了就回傳它的 result 或丟例外。

    resumed：這次是從 WAITING 被認領的（等子 run 的途中被叫醒或備援檢查）。
    從 PENDING / RETRYING 認領代表新的一次嘗試，最新的子 run 已經結束的話要建一個新的；
    只有子 run 還在跑時才沿用它——worker 在「建好子 run」和「轉成 WAITING」之間掛掉、
    被 recover_stale_running_tasks 重新排回來時，不會多建一個。
    """
    latest = next(iter(child_runs(db, task.id)), None)

    if latest is not None and latest.status == WorkFlowStatus.PENDING:
        raise NotReady(FALLBACK_CHECK_SECONDS, f"Waiting for child run {latest.id}")
    
    if latest is not None and resumed:
        if latest.status == WorkFlowStatus.SUCCESS:
            return latest.result or {}
        raise RuntimeError(_failure_message(db, latest))

    child = _start_child(db, task, payload)
    raise NotReady(FALLBACK_CHECK_SECONDS, f"Started child run {child.id}")


def subworkflow_definition_ids(steps: list[dict]) -> set[uuid.UUID]:
    """一份定義的 steps 裡呼叫了哪些定義（格式不對的略過，留給存檔檢查報錯）。"""
    ids = set()
    for step in steps or []:
        if step.get("task_type") != SUBWORKFLOW:
            continue
        try: 
            ids.add(uuid.UUID(str((step.get("payload") or {}).get("definition_id"))))
        except ValueError:
            continue
    return ids


def calls_back_into(db, start_ids: set[uuid.UUID], target_id: uuid.UUID) -> bool:
    """從 start_ids 這些定義沿著 subworkflow 步驟往下走，會不會走回 target_id。"""
    stack, seen = list(start_ids), set()
    while stack:
        current = stack.pop()
        if current == target_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        definition = db.get(WorkflowDefinition, current)
        if definition is not None:
            stack.extend(subworkflow_definition_ids(definition.steps))
    return False

