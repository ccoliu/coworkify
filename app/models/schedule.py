from sqlalchemy.orm import Mapped, mapped_column
import uuid
from datetime import datetime
from typing import List, Any, Optional
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from app.db import Base

class WorkflowSchedule(Base):
    __tablename__ = "workflow_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False) #e.g. "0 9 * * *"
    # 要定期執行的產線。定義被刪掉時這個排程也一起消失（DB 的 ON DELETE CASCADE）——
    # 產線沒了，排程沒有意義。
    definition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    # 每次觸發要餵給定義的輸入，格式與規則同 POST /definitions/{id}/runs
    input: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    # 舊排程（definition_id 是 None）留下的 step 快照。新排程一律指向定義，不再複製 steps。
    steps: Mapped[List[Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    