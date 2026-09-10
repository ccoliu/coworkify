from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from croniter import croniter

from app.schemas.workflow import WorkflowStepCreate

class WorkflowScheduleCreate(BaseModel):
    name: str = Field(..., max_length=255)
    cron_expression: str = Field(..., description="標準5欄位cron，例如每天9點：'0 9 * * *'")
    steps: List[WorkflowStepCreate] = Field(..., min_length=1)
    enabled: bool = True

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError("Invalid cron expression")
        return v

class PromoteWorkflowToSchedule(BaseModel):
    """Turn an already-created Workflow into a recurring Schedule, reusing its stored step template."""

    name: str = Field(..., max_length=255)
    cron_expression: str = Field(..., description="標準5欄位cron，例如每天9點：'0 9 * * *'")
    enabled: bool = True

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError("Invalid cron expression")
        return v


class WorkflowScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    cron_expression: Optional[str] = None
    steps: Optional[List[WorkflowStepCreate]] = None
    enabled: Optional[bool] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
       if v is not None and not croniter.is_valid(v):
            raise ValueError("Invalid cron expression")
       return v

class WorkflowScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    cron_expression: str
    steps: List[WorkflowStepCreate]
    enabled: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime