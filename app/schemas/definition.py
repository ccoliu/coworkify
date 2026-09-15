import math
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.workflow import StepsGraph, WorkflowStepCreate

InputFieldKind = Literal["string", "text", "number", "boolean", "select", "multiselect"]

class InputFieldOption(BaseModel):
    value: str
    label: str

class InputFieldSpec(BaseModel):
    """跟 GET /tasks/types 的 field spec 同形，前端直接用 TaskPayloadFields 畫 run 表單。"""
    key: str = Field(..., pattern=r"^[a-zA-Z0-9_]+$", max_length=100)
    label: str = Field(..., max_length=255)
    kind: InputFieldKind = "string"
    default: Union[bool, int, float, str, List[str], None] = None
    required: bool = False
    help: Optional[str] = None
    options: Optional[List[InputFieldOption]] = None

class WorkflowDefinitionCreate(StepsGraph):
    """建立與整份取代（PUT）共用。"""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    input_schema: List[InputFieldSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input_schema(self):
        keys = [f.key for f in self.input_schema]
        if len(keys) != len(set(keys)):
            raise ValueError("input_schema 的欄位 key 不可重複")
        for f in self.input_schema:
            if f.kind in ("select", "multiselect") and not f.options:
                raise ValueError(f"輸入欄位 '{f.key}' 是 {f.kind}，必須提供 options")
        if self.input_schema and not any(s.task_type == "input" for s in self.steps):
            raise ValueError("定義了 input_schema 就必須有一個 input step，run 的輸入會從那一步進入 workflow")
        return self

class WorkflowRunCreate(BaseModel):
    input: Dict[str, Any] = Field(default_factory=dict)

class WorkflowRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    created_at: datetime

class WorkflowDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    steps: List[WorkflowStepCreate]
    input_schema: List[InputFieldSpec]
    version: int
    created_at: datetime
    updated_at: datetime
    # 由 API 另外掛上去的統計，不是欄位
    run_count: int = 0
    last_run: Optional[WorkflowRunSummary] = None

def _coerce(spec: InputFieldSpec, value):
    kind = spec.kind
    if kind in ("string", "text"):
        if not isinstance(value, str):
            raise ValueError("必須是字串")
        return value
    if kind == "number":
        if isinstance(value, bool):
            raise ValueError("必須是數字")
        if isinstance(value, (int, float)):
            n = value
        elif isinstance(value, str):
            try:
                n = float(value)
            except ValueError:
                raise ValueError(f"'{value}' 不是數字") from None
        else:
            raise ValueError("必須是數字")
        if isinstance(n, float):
            if not math.isfinite(n):
                raise ValueError("必須是有限的數字")
            return int(n) if n.is_integer() else n
        return n
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if value in ("true", "false"):
            return value == "true"
        raise ValueError("必須是 true / false")

    
    allowed = {o.value for o in spec.options or []}
    if kind == "select":
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"'{value}' 不在選項內")
        return value
    
    #multiselect
    if not isinstance(value, list) or any(not isinstance(v, str) or v not in allowed for v in value):
        raise ValueError("必須是選項內的值組成的 list")
    return value

def resolve_run_input(input_schema: list[dict], provided: dict) -> dict:
    """
    依定義的 input_schema 檢查並正規化一次 run 的輸入：補預設值、轉型、擋掉未宣告的欄位。
    錯誤一次收集完再丟，前端才能一次顯示全部問題。
    沒填的選填欄位會是 None（multiselect 是 []），讓下游看到的結構每次都一樣。
    """
    specs = [InputFieldSpec.model_validate(f) for f in input_schema]
    known = {s.key for s in specs}
    errors = [f"未宣告的輸入欄位 '{k}'" for k in provided if k not in known]

    resolved: dict = {}
    for spec in specs:
        value = provided.get(spec.key, spec.default)
        if value is None or value == "" or value == []:
            if spec.required:
                errors.append(f"輸入欄位 '{spec.label}' 必填")
            resolved[spec.key] = [] if spec.kind == "multiselect" else None
            continue
        try:
            resolved[spec.key] = _coerce(spec, value)
        except ValueError as e:
            errors.append(f"輸入欄位 '{spec.label}': {e}")
    
    if errors:
        raise ValueError("\n".join(errors))
    return resolved