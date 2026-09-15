from pydantic._internal._known_annotated_metadata import UUID_CONSTRAINTS
import uuid
from datetime import datetime
from typing import Any, List, Optional
from enum import Enum
from sqlalchemy import UUID, String, Text, DateTime, JSON, ForeignKey, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class WorkFlowStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class WorkflowDefinition(Base):
    """
    一條「產線」：步驟樣板 + 輸入規格。本身不執行——每次執行是一筆 Workflow（run）。
    run 建立時會把當下的 steps 複製一份到自己的 steps_template，之後改定義不會改寫歷史。
    """
    __tablename__ = "workflow_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index = True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # WorkflowStepCreate 的 dict list
    steps: Mapped[List[Any]] = mapped_column(JSON, nullable=False)
    # InputFieldSpec 的 dict list，跟 GET /tasks/types 的 field spec 同形
    input_schema: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)
    # steps 或 input_schema 有變才 +1；run 記下自己用的是哪一版
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())


class Workflow(Base):
    __tablename__ = "workflows"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=WorkFlowStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    # 建立時的原始 WorkflowStepCreate dict list，供「把這個 workflow 升級成排程」
    # 使用（一個 workflow 建立後只留展開的 Task/WorkflowStep，原始樣板本來不會保留）。
    # 舊資料（此欄位新增前建立的 workflow）會是 None。
    steps_template: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True, default=None)
    # workflow 的「成品」：所有終端 step 的成功結果，在整條 workflow 轉成
    # SUCCESS 時由 executor 收集寫入。失敗或還在跑的 workflow 是 None。
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    steps: Mapped[List["WorkflowStep"]] = relationship(
        "WorkflowStep", back_populates="workflow", cascade="all, delete-orphan"
    )
    # 這次 run 屬於哪條產線。舊資料、以及直接打 POST /workflows/ 建立的一次性 workflow 是 None；
    # 定義被刪掉時 DB 會設回 NULL（run 的紀錄保留）。
    definition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    definition_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 這次 run 經 input_schema 檢查、補完預設值後的輸入；rerun 會沿用它
    input: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)

class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, unique=True)
    # 此 step 要等哪些 task 完成才能派送(存 task id 字串陣列)
    depends_on: Mapped[List] = mapped_column(JSON, nullable=False, default=list)
    # 非 None 代表這是 reduce 步驟，值為它要收斂的 for_each step key。
    # 建立時 depends_on 是空的，等那組模板展開後才被填成所有展開出來的 task id。
    reduce_of_key: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    # 非 None 代表這個 step 是條件分支的其中一邊：branch_of_key 是那個 condition
    # step 的 key，branch_when 是 "true"/"false"。condition 執行完後，
    # advance_workflow 會比對它的 {"passed": bool} 結果跟 branch_when 是否相符——
    # 不符的那一邊（連同它自己的下游）直接被取消，符合的那一邊照一般 depends_on
    # 邏輯往下派送。這樣 condition 本身永遠是 SUCCESS，不用靠「失敗」硬做分支。
    branch_of_key: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    branch_when: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)
    # 建立時的本地識別碼，讓下游可以用 '{{steps.<key>.result}}' 參照這一步的結果。
    # 只有 concrete step 有；for_each 展開出來的 task 共用同一個模板 key，
    # 會造成參照歧義，所以一律留 None。
    step_key: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="steps")


class WorkflowStepTemplate(Base):
    """
    for_each 動態展開用的步驟模板：建立 workflow 時先存起來，
    等 for_each_task_id 對應的 task 成功並回傳一份 list 之後，
    才依 list 內每個項目各自展開成真正的 Task + WorkflowStep。
    """
    __tablename__ = "workflow_step_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_template: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # 依賴的其他「同一組 for_each」模板的 key（不是這個 for_each_task_id 本身）
    depends_on_keys: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    for_each_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    expanded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
