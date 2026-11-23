from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OnStatus = Literal["success", "failed", "any"]


def _check_paths(value: Dict[str, Any], *, values_are_paths: bool) -> Dict[str, Any]:
    for key, path in value.items():
        if not str(key).strip():
            raise ValueError("鍵不能是空字串")
        if values_are_paths and (not isinstance(path, str) or not path.strip()):
            raise ValueError(f"'{key}' 的路徑必須是非空字串，例如 'head_commit.id'")
    return value


class WorkflowTriggerCreate(BaseModel):
    name: str = Field(..., max_length=255)
    kind: Literal["webhook", "workflow"] = "webhook"
    # 要啟動的產線
    definition_id: UUID
    # kind = workflow 才用：看哪條產線的 run 結束、什麼結果算數
    source_definition_id: Optional[UUID] = None
    on_status: OnStatus = "success"
    # run 輸入欄位 → 路徑
    input_mapping: Dict[str, str] = Field(default_factory=dict)
    # 路徑 → 期望值（list = 其中之一）
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

    @model_validator(mode="after")
    def source_matches_kind(self):
        if self.kind == "workflow" and self.source_definition_id is None:
            raise ValueError("a workflow trigger needs source_definition_id")
        if self.kind == "webhook" and self.source_definition_id is not None:
            raise ValueError("source_definition_id only applies to workflow triggers")
        return self


class WorkflowTriggerUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    input_mapping: Optional[Dict[str, str]] = None
    filter: Optional[Dict[str, Any]] = None
    on_status: Optional[OnStatus] = None
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
    kind: str
    definition_id: UUID
    source_definition_id: Optional[UUID] = None
    on_status: Optional[str] = None
    input_mapping: Dict[str, str]
    filter: Dict[str, Any]
    enabled: bool
    last_triggered_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # webhook 才有：外部系統要打的路徑，前面接上 API 的對外網址
    hook_path: Optional[str] = None


class WorkflowTriggerWithSecret(WorkflowTriggerResponse):
    """建立與換 secret 時回傳；webhook 的 secret 只會出現這一次，workflow 觸發器沒有 secret。"""

    secret: Optional[str] = None
