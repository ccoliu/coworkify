import re
import time
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Optional
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models.task import Task, TaskStatus
from app.models.task_log import TaskLog
from app.tasks.handler import get_task_handler, TASK_REGISTRY
import os
import redis
import json
from sqlalchemy import select
from app.models.workflow import Workflow, WorkflowStep, WorkFlowStatus, WorkflowStepTemplate

REDIS_URL = os.getenv("REDIS_URL")
redis_publisher = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def notify_status_change(task_id: str, status: str, result=None, error=None):
    event = {
        "task_id": task_id,
        "status": status,
        "result": result,
        "error": error,
        "timestamp": time.time()
    }
    redis_publisher.publish("task_updates", json.dumps(event))

@celery_app.task(bind=True, name="coworkify.execute_task")
def execute_task(self, task_id: str):
    db = SessionLocal()
    start_time = time.time()
    task_uuid = uuid.UUID(task_id)

    try:
        task = db.get(Task, task_uuid)
        if not task:
            return f"Task {task_uuid} not found"

        if task.status == TaskStatus.RUNNING or task.status == TaskStatus.SUCCESS or task.status == TaskStatus.FAILED:
            return f"Task {task_uuid} is already {task.status}"

        # 1. 更新狀態為 RUNNING (idempotent)
        task.status = TaskStatus.RUNNING if (task.status == TaskStatus.PENDING or task.status == TaskStatus.RETRYING) else task.status
        notify_status_change(str(task.id), TaskStatus.RUNNING, None, None)
       
        # 2. 尋找對應的 handler
        handler = get_task_handler(task.task_type)
        if not handler:
            raise ValueError(f"Unknown task type: {task.task_type}. Available types: {list(TASK_REGISTRY.keys())}")
        
        # 3. 記錄任務開始
        result = handler(task.payload)
        execute_time_ms = (time.time() - start_time) * 1000

        # 4. 執行成功
        record_task_success(db, task, result, execute_time_ms)
        return result

    except Exception as exc:
        execute_time_ms = (time.time() - start_time) * 1000
        task = db.get(Task, task_uuid)

        if task:
            countdown = record_task_failure(db, task, str(exc), execute_time_ms)
            db.close()
            if countdown is not None:
                raise self.retry(countdown=countdown, exc=exc)

        raise exc
    finally:
        db.close()


def record_task_success(db, task: Task, result, execute_time_ms: float = 0.0):
    """把一個 task 標記成功，寫 log、推播狀態、觸發 workflow 後續派送。
    Celery 執行路徑（execute_task）跟本機 runner 回報路徑共用這個函式。"""
    task.status = TaskStatus.SUCCESS
    notify_status_change(str(task.id), TaskStatus.SUCCESS, result, None)
    db.add(TaskLog(
        task_id=task.id,
        status=TaskStatus.SUCCESS,
        result=result,
        execution_time_ms=execute_time_ms,
    ))
    db.commit()
    advance_workflow(db, task)


def record_task_failure(db, task: Task, error_message: str, execute_time_ms: float = 0.0) -> Optional[int]:
    """
    記錄一次失敗。還有重試次數的話轉成 RETRYING 並回傳這次該等待的秒數
    （Celery 路徑用它 self.retry(countdown=...)；本機 runner 路徑則把
    task.scheduled_at 往後推，等下次輪詢時間到了才會再被認領）。
    重試次數用完就標記 FAILED、串連取消下游，回傳 None。
    """
    if task.retry_count < task.max_retries:
        task.retry_count += 1
        task.status = TaskStatus.RETRYING
        countdown = 2 ** task.retry_count  # Exponential Backoff
        task.scheduled_at = datetime.utcnow() + timedelta(seconds=countdown)

        notify_status_change(str(task.id), TaskStatus.RETRYING, None, error_message)
        db.add(TaskLog(
            task_id=task.id,
            status=TaskStatus.RETRYING,
            error_message=f"Attempt {task.retry_count} failed: {error_message}. Retrying in {countdown}s...",
            execution_time_ms=execute_time_ms,
        ))
        db.commit()
        return countdown
    else:
        task.status = TaskStatus.FAILED
        notify_status_change(str(task.id), TaskStatus.FAILED, None, error_message)
        db.add(TaskLog(
            task_id=task.id,
            status=TaskStatus.FAILED,
            error_message=f"Maximum retries ({task.max_retries}) exceeded: {error_message}",
            execution_time_ms=execute_time_ms,
        ))
        db.commit()
        advance_workflow(db, task)
        return None


def dispatch_task(task: Task):
    """派送一個 pending task：有指定 runner 的留給本機 runner 去 /runner/tasks/next 認領，
    否則跟以前一樣丟進 Celery 佇列給共用 worker 執行。"""
    if task.runner_id:
        return
    execute_task.apply_async(args=[str(task.id)], priority=task.priority)
        
def advance_workflow(db, task: Task):
    """task 成功/失敗後，更新 workflow 狀態並派送後續節點"""
    steps = db.scalars(select(WorkflowStep).where(WorkflowStep.task_id == task.id)).first()
    if not steps:
        return

    workflow = db.get(Workflow, steps.workflow_id)

    if task.status == TaskStatus.SUCCESS:
        # 若這個 task 是某個 for_each 分支的來源，先展開動態步驟，
        # 展開後才能在下面用完整的 all_steps 判斷是否全部完成
        expand_dynamic_steps(db, workflow, task)

        all_steps = db.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id)).all()

        # 找出依賴這個 task、並且依賴已全部滿的下游step，派送出去
        for s in all_steps:
            if str(task.id) not in s.depends_on:
                continue
            dep_tasks = db.scalars(select(Task).where(Task.id.in_(s.depends_on))).all()
            if all(t.status == TaskStatus.SUCCESS for t in dep_tasks):
                next_task = db.get(Task, s.task_id)
                if next_task.status == TaskStatus.PENDING:
                    dispatch_task(next_task)
    
        # 檢查是否所有 task 都完成了
        all_tasks = db.scalars(select(Task).where(Task.id.in_([s.task_id for s in all_steps]))).all()
        if all(t.status == TaskStatus.SUCCESS for t in all_tasks):
            workflow.status = WorkFlowStatus.SUCCESS
            db.commit()

    elif task.status == TaskStatus.FAILED:
        # 這個 task 失敗了：把所有下游(直接+間接依賴它的)step 取消掉，整條 workflow 標記失敗
        all_steps = db.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id)).all()
        to_cancel_ids = set()
        frontier = [task.id]
        while frontier:
            current = frontier.pop()
            for s in all_steps:
                if str(current) in s.depends_on and s.task_id not in to_cancel_ids:
                    to_cancel_ids.add(s.task_id)
                    frontier.append(s.task_id)
            
        for tid in to_cancel_ids:
            t = db.get(Task, tid)
            if t and t.status == TaskStatus.PENDING:
                t.status = TaskStatus.CANCELLED
                notify_status_change(str(t.id), TaskStatus.CANCELLED, None, "上游任務失敗，已取消")

        workflow.status = WorkFlowStatus.FAILED
        db.commit()
    
def create_workflow_from_steps(db, name: str, steps: list[dict]) -> Workflow:
    """建立 workflow + 派送根節點；供 API 與排程共用"""
    workflow = Workflow(name=name, status="pending")
    db.add(workflow)
    db.flush()

    concrete_steps = [s for s in steps if not s.get("for_each")]
    template_steps = [s for s in steps if s.get("for_each")]

    key_to_task: dict[str, Task] = {}
    for step in concrete_steps:
        task = Task(
            name=step["name"],
            task_type=step["task_type"],
            payload=step["payload"],
            priority=step["priority"],
            max_retries=step.get("max_retries", 3),
            runner_id=step.get("runner_id"),
            status="pending",
        )
        db.add(task)
        key_to_task[step["key"]] = task
    db.flush()

    ws_list: list[WorkflowStep] = []
    for step in concrete_steps:
        ws = WorkflowStep(
            workflow_id=workflow.id,
            task_id=key_to_task[step["key"]].id,
            depends_on=[str(key_to_task[dep].id) for dep in step.get("depends_on", [])],
        )
        db.add(ws)
        ws_list.append(ws)

    for step in template_steps:
        map_task = key_to_task.get(step["for_each"])
        if map_task is None:
            raise ValueError(f"for_each 指向的 step '{step['for_each']}' 不存在或本身也是動態步驟")
        tmpl = WorkflowStepTemplate(
            workflow_id=workflow.id,
            key=step["key"],
            name=step["name"],
            task_type=step["task_type"],
            payload_template=step.get("payload", {}),
            priority=step.get("priority", 3),
            max_retries=step.get("max_retries", 3),
            depends_on_keys=step.get("depends_on", []),
            for_each_task_id=map_task.id,
            runner_id=step.get("runner_id"),
        )
        db.add(tmpl)

    db.commit()
    db.refresh(workflow)

    for step, ws in zip(concrete_steps, ws_list):
        if not step.get("depends_on"):
            task = key_to_task[step["key"]]
            dispatch_task(task)

    return workflow


_ITEM_PLACEHOLDER = re.compile(r"\{\{\s*item(?:\.([a-zA-Z0-9_.]+))?\s*\}\}")


def _resolve_item_path(item, path: str | None):
    if not path:
        return item
    value = item
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def render_payload(template: dict, item):
    """把 payload_template 裡的 '{{item}}' / '{{item.欄位}}' 換成該 for_each 項目的實際值"""
    def render_value(value):
        if isinstance(value, str):
            stripped = value.strip()
            full_match = _ITEM_PLACEHOLDER.fullmatch(stripped)
            if full_match:
                return _resolve_item_path(item, full_match.group(1))
            return _ITEM_PLACEHOLDER.sub(
                lambda m: str(_resolve_item_path(item, m.group(1))), value
            )
        if isinstance(value, dict):
            return {k: render_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [render_value(v) for v in value]
        return value

    return render_value(template)


def expand_dynamic_steps(db, workflow: Workflow, map_task: Task):
    """
    map_task 成功後，找出以它為 for_each 來源、尚未展開的模板，
    依它的執行結果（必須是一個 list）逐項展開成真正的 Task + WorkflowStep。
    """
    templates = db.scalars(
        select(WorkflowStepTemplate).where(
            WorkflowStepTemplate.for_each_task_id == map_task.id,
            WorkflowStepTemplate.expanded == False,
        )
    ).all()
    if not templates:
        return

    log = db.scalars(
        select(TaskLog)
        .where(TaskLog.task_id == map_task.id, TaskLog.status == TaskStatus.SUCCESS)
        .order_by(TaskLog.created_at.desc())
    ).first()
    items = log.result if log and isinstance(log.result, list) else []

    # item_index -> template key -> 展開出來的 task id
    expanded_task_ids: dict[int, dict[str, uuid.UUID]] = {}

    for i, item in enumerate(items):
        expanded_task_ids[i] = {}
        for template in templates:
            task = Task(
                name=f"{template.name} [{i + 1}]",
                task_type=template.task_type,
                payload=render_payload(template.payload_template, item),
                priority=template.priority,
                max_retries=template.max_retries,
                runner_id=template.runner_id,
                status="pending",
            )
            db.add(task)
            db.flush()
            expanded_task_ids[i][template.key] = task.id

        for template in templates:
            if template.depends_on_keys:
                depends_on = [str(expanded_task_ids[i][k]) for k in template.depends_on_keys]
            else:
                # 這一支分支的根節點：等 map_task 完成即可執行（map_task 此時已經成功了）
                depends_on = [str(map_task.id)]
            db.add(
                WorkflowStep(
                    workflow_id=workflow.id,
                    task_id=expanded_task_ids[i][template.key],
                    depends_on=depends_on,
                )
            )

    for template in templates:
        template.expanded = True

    db.commit()

    for task_ids in expanded_task_ids.values():
        for template in templates:
            if not template.depends_on_keys:
                task_id = task_ids[template.key]
                t = db.get(Task, task_id)
                dispatch_task(t)


