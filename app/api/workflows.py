from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowStep
from app.schemas.workflow import WorkflowCreate, WorkflowResponse
from app.tasks.executor import execute_task
from app.core.security import verify_api_key
from app.core.rate_limit import RateLimiter

router = APIRouter(
    prefix='/workflows',
    tags=['Workflows'],
    dependencies=[Depends(verify_api_key), Depends(RateLimiter(times=5000, seconds=1))]
)

@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    workflow = Workflow(name=payload.name, status="pending")
    db.add(workflow)
    db.flush() # 取得 workflow.id

    key_to_task: dict[str, Task] = {}
    for step in payload.steps:
        task = Task(
            name = step.name,
            task_type = step.task_type,
            payload = step.payload,
            priority = step.priority,
            max_retries = step.max_retries,
            status = "pending",
        )
        db.add(task)
        key_to_task[step.key] = task
    db.flush() # 產生 task_id

    steps: list[WorkflowStep] = []
    for step in payload.steps:
        ws = WorkflowStep(
            workflow_id=workflow.id,
            task_id=key_to_task[step.key].id,
            depends_on=[str(key_to_task[dep].id) for dep in step.depends_on]
        )
        db.add(ws)
        steps.append(ws)

    db.commit()
    db.refresh(workflow)

    # 派送沒有依賴的根結點
    for step, ws in zip(payload.steps, steps):
        if not step.depends_on:
            task = key_to_task[step.key]
            execute_task.apply_async(args=[str(task.id)], priority=task.priority)

    for ws in workflow.steps:
        ws.task_status = "pending"
    return workflow

@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    task_ids = [s.task_id for s in workflow.steps]
    tasks_by_id = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(task_ids))).all()}
    for s in workflow.steps:
        s.task_status = tasks_by_id[s.task_id].status

    return workflow        

    
