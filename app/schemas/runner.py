from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class RunnerCreate(BaseModel):
    name: str = Field(..., max_length=255)


class RunnerCreated(BaseModel):
    """建立當下才回傳一次的完整資訊，token 之後就拿不到了"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    token: str
    created_at: datetime


class RunnerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class RunnerTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    task_type: str
    payload: dict
    priority: int


class RunnerTaskComplete(BaseModel):
    status: Literal["success", "failed"]
    result: Optional[Any] = None
    error: Optional[str] = None
