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
    created_at: datetime
    updated_at: datetime

class TaskResultResponse(BaseModel):
    """
    最新一筆 TaskLog 的內容。任務結果目前只會透過 /ws/tasks 廣播一次，事後查不到，
    這個 endpoint 補上事後查詢的路徑（例如 CoworkifyExecutor 這種輪詢的呼叫端）。
    """
    task_id: UUID
    status: str
    result: Optional[Any] = None
    error_message: Optional[str] = None