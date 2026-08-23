import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import UUID, String, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="online")
    current_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=func.now())
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
