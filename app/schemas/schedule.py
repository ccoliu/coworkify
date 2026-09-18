from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from croniter import croniter

from app.schemas.workflow import WorkflowStepCreate

def _check_cron(v: str) -> str:
    if not croniter.is_valid(v):
        raise ValueError("Invalid cron expression")
    return v

class WorkflowScheduleCreate(BaseModel):
    name: str = Field(..., max_length=255)
    cron_expression: str = Field(..., description="標準5欄位cron，例如每天9點：'0 9 * * *'")
    # 排程指向一條產線，不再自己複製一份 steps——改了定義，下次觸發就用新版
    definition_id: UUID
    input: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        return _check_cron(v)

class PromoteWorkflowToSchedule(BaseModel):
    """把一次已經跑過的 run 變成週期性排程，沿用它的定義與輸入。"""

    name: str = Field(..., max_length=255)
    cron_expression: str = Field(..., description="標準5欄位cron，例如每天9點：'0 9 * * *'")
    enabled: bool = True
    
    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        return _check_cron(v)


class WorkflowScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    cron_expression: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
       return None if v is None else _check_cron(v)

class WorkflowScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    cron_expression: str
    definition_id: Optional[UUID] = None
    input: Optional[Dict[str, Any]] = None
    # 舊排程才有；新排程的步驟在定義裡
    steps: Optional[List[WorkflowStepCreate]] = None
    enabled: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # API 另外掛上去的，方便列表直接顯示
    definition_name: Optional[str] = None
    definition_version: Optional[int] = None