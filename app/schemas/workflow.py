from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowStepCreate(BaseModel):
    key: str = Field(..., description="此步驟在這次請求內的本地識別碼，用來描述依賴關係，不是真正的 task id")
    name: str = Field(..., max_length=255)
    task_type: str = Field(..., max_length=50)
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=3, ge=0)
    max_retries: int = Field(default=3, ge=0)
    depends_on: List[str] = Field(default_factory=list, description="依賴的其他 step 的 key")
    runner_id: Optional[UUID] = Field(
        default=None, description="若設定，此步驟不會派到共用 worker，改由對應的本機 runner 認領執行"
    )
    for_each: Optional[str] = Field(
        None,
        description=(
            "若設定，此步驟不會立即建立成真正的 task，而是等指定 step（其結果必須是一個 list）"
            "成功後，依 list 內每個項目各自展開成一份 task。payload 內可用 '{{item}}' "
            "或 '{{item.欄位名}}' 參照該項目的值。"
        ),
    )


class WorkflowCreate(BaseModel):
    name: str = Field(..., max_length=255)
    steps: List[WorkflowStepCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_dag(self):
        keys = [s.key for s in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("Step key 不可重複")
        key_set = set(keys)
        by_key = {s.key: s for s in self.steps}
        deps = {s.key: s.depends_on for s in self.steps}

        for key, deps_keys in deps.items():
            for dep in deps_keys:
                if dep not in key_set:
                    raise ValueError(f"Step '{key}' 依賴的 '{dep}' 不存在")
                if dep == key:
                    raise ValueError(f"Step '{key}' 不能依賴自己")

        for step in self.steps:
            if not step.for_each:
                for dep in step.depends_on:
                    if by_key[dep].for_each:
                        raise ValueError(
                            f"Step '{step.key}' 不能依賴動態展開步驟 '{dep}'（目前不支援 fan-in/reduce）"
                        )
                continue

            if step.for_each not in key_set:
                raise ValueError(f"Step '{step.key}' 的 for_each 指向不存在的 step '{step.for_each}'")
            if step.for_each == step.key:
                raise ValueError(f"Step '{step.key}' 不能 for_each 自己")
            if by_key[step.for_each].for_each:
                raise ValueError(
                    f"Step '{step.key}' 的 for_each 目標 '{step.for_each}' 本身也是動態展開步驟，不支援巢狀展開"
                )
            for dep in step.depends_on:
                if by_key[dep].for_each != step.for_each:
                    raise ValueError(
                        f"Step '{step.key}' 是 for_each='{step.for_each}' 的動態步驟，"
                        f"depends_on 只能參照同一組的其他動態步驟，不可依賴 '{dep}'"
                    )

        # loop detection
        WHITE, GRAY, BLACK = 0,1,2
        color = {k: WHITE for k in key_set}

        def dfs(node: str):
            color[node] = GRAY
            for dep in deps[node]:
                if color[dep] == GRAY:
                    raise ValueError(f"workflow 存在循環依賴: '{node}' <-> '{dep}'")
                if color[dep] == WHITE:
                    dfs(dep)
            color[node] = BLACK

        for key in key_set:
            if color[key] == WHITE:
                dfs(key)

        return self

class WorkflowStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    depends_on: List[UUID]
    task_status: Optional[str] = None
    task_name: Optional[str] = None
    task_type: Optional[str] = None
    task_runner_id: Optional[UUID] = None

class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime
    steps: List[WorkflowStepResponse]