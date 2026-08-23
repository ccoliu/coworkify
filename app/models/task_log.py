import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import UUID, String, DateTime, JSON, Text, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    worker_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("workers.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
