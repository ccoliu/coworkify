from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.models.runner import Runner
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.runner import RunnerCreate, RunnerCreated, RunnerResponse
from app.core.security import get_current_user, generate_runner_token, hash_runner_token
from app.core.rate_limit import RateLimiter

router = APIRouter(
    prefix="/runners",
    tags=["Runners"],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))],
)


@router.post("/", response_model=RunnerCreated, status_code=status.HTTP_201_CREATED)
def create_runner(
    payload: RunnerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token = generate_runner_token()
    runner = Runner(
        name=payload.name,
        owner_id=current_user.id,
        token_hash=hash_runner_token(token),
    )
    db.add(runner)
    db.commit()
    db.refresh(runner)
    # token 只有這一次會完整回傳，之後只存得到雜湊
    return RunnerCreated(id=runner.id, name=runner.name, token=token, created_at=runner.created_at)


@router.get("/", response_model=List[RunnerResponse])
def list_runners(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.scalars(
        select(Runner).where(Runner.owner_id == current_user.id).order_by(Runner.created_at.desc())
    ).all()


@router.delete("/{runner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_runner(
    runner_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runner = db.get(Runner, runner_id)
    if not runner or runner.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runner not found")

    still_pending = db.scalars(
        select(Task).where(
            Task.runner_id == runner.id,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.RETRYING]),
        )
    ).first()
    if still_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此 runner 還有未完成的任務，無法刪除",
        )

    db.delete(runner)
    db.commit()
    return None
