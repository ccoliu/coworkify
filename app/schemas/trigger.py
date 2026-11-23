from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _check_paths(value: Dict[str, Any], *, values_are_paths: bool) -> Dict[str, Any]:
    for key, path in value.items():
        if not str(key).strip():
            raise ValueError("鍵不能是空字串")
        if values_are_paths and (not isinstance(path, str) or not path.strip()):
            raise ValueError(f"'{key}' 的路徑必須是非空字串，例如 'head_commit.id'")
    return value


class WorkflowTriggerCreate(BaseModel):
    name: str = Field(..., max_length=255)
    definition_id: UUID
    # run 輸入欄位 → body 路徑
    input_mapping: Dict[str, str] = Field(default_factory=dict)
    # body 路徑 → 期望值（list = 其中之一）
    filter: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("input_mapping")
    @classmethod
    def validate_mapping(cls, v):
        return _check_paths(v, values_are_paths=True)

    @field_validator("filter")
    @classmethod
    def validate_filter(cls, v):
        return _check_paths(v, values_are_paths=False)


class WorkflowTriggerUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    input_mapping: Optional[Dict[str, str]] = None
    filter: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None

    @field_validator("input_mapping")
    @classmethod
    def validate_mapping(cls, v):
        return None if v is None else _check_paths(v, values_are_paths=True)

    @field_validator("filter")
    @classmethod
    def validate_filter(cls, v):
        return None if v is None else _check_paths(v, values_are_paths=False)


class WorkflowTriggerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    definition_id: UUID
    input_mapping: Dict[str, str]
    filter: Dict[str, Any]
    enabled: bool
    last_triggered_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # 外部系統要打的路徑，前面接上 API 的對外網址
    hook_path: str = ""


class WorkflowTriggerWithSecret(WorkflowTriggerResponse):
    """只有建立與換 secret 時回傳；之後再也拿不到原文。"""

    secret: str
