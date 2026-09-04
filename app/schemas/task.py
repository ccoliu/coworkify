from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class TaskCreate(BaseModel):
    name: str = Field(..., max_length=255, description="任務名稱")
    task_type: str = Field(..., max_length=50, description="任務類型")
    payload: Dict[str, Any] = Field(default_factory=dict, description="任務參數")
    priority: int = Field(default=0, ge=0, le=10, description="任務優先級(0~10)")
    max_retries: int = Field(default=3, ge=0, description="最大重試次數")
    scheduled_at: Optional[datetime] = Field(default=None, description="預定執行時間")
    runner_id: Optional[UUID] = Field(
        default=None, description="若設定，此任務不會派到共用 worker，改由對應的本機 runner 認領執行"
    )

class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    task_type: str
    payload: Dict[str, Any]
    status: str
    priority: int
    max_retries: int
    retry_count: int
    scheduled_at: Optional[datetime]
    runner_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime