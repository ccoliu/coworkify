from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
import json 
import re

_STEP_REF = re.compile(r"\{\{\s*steps\.([a-zA-Z0-9_]+)\.result(?:\.[a-zA-Z0-9_]+)*\s*\}\}")
_STEP_REF_SYNTAX = "{{steps.<key>.result}}"

def _referenced_step_keys(payload: dict) -> set[str]:
    return set(_STEP_REF.findall(json.dumps(payload, ensure_ascii=False)))

class WorkflowStepCreate(BaseModel):
    key: str = Field(..., description="此步驟在這次請求內的本地識別碼，用來描述依賴關係，不是真正的 task id")
    name: str = Field(..., max_length=255)
    task_type: str = Field(..., max_length=50)
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=3, ge=0)
    max_retries: int = Field(default=3, ge=0)
    depends_on: List[str] = Field(default_factory=list, description="依賴的其他 step 的 key")
    for_each: Optional[str] = Field(
        None,
        description=(
            "若設定，此步驟不會立即建立成真正的 task，而是等指定 step（其結果必須是一個 list）"
            "成功後，依 list 內每個項目各自展開成一份 task。payload 內可用 '{{item}}' "
            "或 '{{item.欄位名}}' 參照該項目的值。"
        ),
    )

    reduce_of: str | None = Field(None, description="指向某個 for_each step 的 key。若設定，會將所有 for_each task 的結果合併成一個 list，並取代 for_each 本身建立一個新的 task（這是一個 reduce 操作）。")

    branch_of: Optional[str] = Field(
        None,
        description=(
            "指向某個 condition step 的 key。若設定，這個 step 只有在該 condition 的"
            "結果符合 branch_when 時才會執行，否則會被取消（連同它自己的下游）——"
            "用來實現 if/else 分支。必須同時把 branch_of 指向的 step 加進 depends_on。"
        ),
    )
    branch_when: Optional[Literal["true", "false"]] = Field(
        None, description="搭配 branch_of 使用：這個分支要在 condition 結果是 true 還是 false 時執行。"
    )

class StepsGraph(BaseModel):
    """steps + DAG 驗證；一次性 workflow 與 workflow definition 共用。"""
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

        input_keys = [s.key for s in self.steps if s.task_type == "input"]
        if len(input_keys) > 1:
            raise ValueError(
                f"一個 workflow 只能有一個 input step（目前有 {len(input_keys)} 個："
                f"{', '.join(input_keys)}）"
            )

        for step in self.steps:
            refs = _referenced_step_keys(step.payload)
            if refs:
                if step.for_each:
                    raise ValueError(
                        f"Step '{step.key}' 是動態展開步驟，payload 目前不支援 {_STEP_REF_SYNTAX} 參照；"
                        f"請用 '{{{{item}}}}' 取得該項目的值"
                    )
                if step.reduce_of:
                    raise ValueError(
                        f"Step '{step.key}' 是 reduce 步驟，請用 '{{{{items}}}}' 取得上游結果"
                    )
                for ref in refs:
                    if ref == step.key:
                        raise ValueError(f"Step '{step.key}' 的 payload 不能參照自己的結果")
                    if ref not in key_set:
                        raise ValueError(f"Step '{step.key}' 的 payload 參照了不存在的 step '{ref}'")
                    if ref not in step.depends_on:
                        raise ValueError(
                            f"Step '{step.key}' 的 payload 參照了 '{ref}' 的結果，"
                            f"必須把 '{ref}' 加進 depends_on，否則無法保證它先執行"
                        )

            if step.task_type == "input" and step.depends_on:
                raise ValueError(
                    f"Step '{step.key}' 是 input step，它是整條 workflow 的資料入口，不能有上游依賴"
                )

            # condition 的 left 留空時，executor 只能在「剛好一個上游」的情況自動帶入
            # 結果（見 app/tasks/executor.py 的 resolve_condition_left）。這裡先擋掉，
            # 否則錯誤要等 task 重試耗盡才浮出來，下游分支還會被連坐取消。
            if step.task_type == "condition" and step.payload.get("left") in (None, ""):
                if len(step.depends_on) != 1:
                    raise ValueError(
                        f"Step '{step.key}' 是 condition 且沒填 payload.left，"
                        f"必須剛好依賴一個上游 step 讓系統自動帶入結果"
                        f"（目前有 {len(step.depends_on)} 個）。"
                        f"或明確指定 left，例如 '{_STEP_REF_SYNTAX}'"
                    )

            if step.for_each and step.reduce_of:
                raise ValueError(f"Step '{step.key}' 不能同時 for_each 和 reduce_of")

            if step.branch_of or step.branch_when:
                if not step.branch_of or not step.branch_when:
                    raise ValueError(f"Step '{step.key}' 的 branch_of 和 branch_when 要一起設定")
                if step.for_each or step.reduce_of:
                    raise ValueError(
                        f"Step '{step.key}' 不能同時是 branch 步驟又是 for_each/reduce_of 步驟（這輪不支援）"
                    )
                if step.branch_of not in key_set:
                    raise ValueError(f"Step '{step.key}' 的 branch_of 指向不存在的 step '{step.branch_of}'")
                if step.branch_of == step.key:
                    raise ValueError(f"Step '{step.key}' 不能 branch 自己")
                if by_key[step.branch_of].task_type != "condition":
                    raise ValueError(
                        f"Step '{step.key}' 的 branch_of 目標 '{step.branch_of}' 不是 condition 步驟"
                    )
                if step.branch_of not in step.depends_on:
                    raise ValueError(
                        f"Step '{step.key}' 用 branch_of='{step.branch_of}' 做分支，"
                        f"必須把 '{step.branch_of}' 也加進 depends_on，確保執行順序"
                    )

            if step.reduce_of:
                if step.reduce_of not in key_set:
                    raise ValueError(f"Step '{step.key}' 的 reduce_of 指向不存在的 step '{step.reduce_of}'")
                if step.reduce_of == step.key:
                    raise ValueError(f"Step '{step.key}' 不能 reduce 自己")
                if not by_key[step.reduce_of].for_each:
                    raise ValueError(
                        f"Step '{step.key}' 的 reduce_of 目標 '{step.reduce_of}' 不是動態展開步驟；"
                        f"reduce_of 只能指向有設 for_each 的 step"
                    )
                if step.depends_on:
                    raise ValueError(
                        f"Step '{step.key}' 是 reduce 步驟，依賴關係在 '{step.reduce_of}' 展開後自動決定，"
                        f"不可自行指定 depends_on"
                    )
                continue
                
            if not step.for_each:
                for dep in step.depends_on:
                    if by_key[dep].for_each:
                        raise ValueError(
                            f"Step '{step.key}' 不是 for_each 步驟，但依賴了動態展開步驟 '{dep}'；"
                            f"要做 fan-in 請改用 reduce_of='{dep}'"
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

class WorkflowCreate(BaseModel):
    name: str = Field(..., max_length=255)
    

class WorkflowStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    depends_on: List[UUID]
    branch_of_key: Optional[str] = None
    branch_when: Optional[str] = None
    # 前端畫布要靠 step_key 把 branch_of_key（存的是 key 不是 task id）解析成節點 id；
    # reduce_of_key 讓 reduce 步驟在圖上標示出來。
    step_key: Optional[str] = None
    reduce_of_key: Optional[str] = None
    task_status: Optional[str] = None
    task_name: Optional[str] = None
    task_type: Optional[str] = None

class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime
    steps: List[WorkflowStepResponse]
    # None for a workflow created before this field existed — the frontend
    # uses this to decide whether "promote to schedule" is even offered.
    steps_template: Optional[List[Dict[str, Any]]] = None
    # 整條 workflow 成功時收集的終端結果；失敗或執行中是 None
    result: Optional[Dict[str, Any]] = None
    definition_id: Optional[UUID] = None
    definition_version: Optional[int] = None
    input: Optional[Dict[str, Any]] = None