from pydantic._internal._known_annotated_metadata import UUID_CONSTRAINTS
import uuid
from datetime import datetime
from typing import List
from enum import Enum
from sqlalchemy import UUID, String, DateTime, JSON, ForeignKey, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class WorkFlowStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class Workflow(Base):
    __tablename__ = "workflows"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=WorkFlowStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    steps: Mapped[List["WorkflowStep"]] = relationship(
        "WorkflowStep", back_populates="workflow", cascade="all, delete-orphan"
    )

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
