import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import UUID, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Runner(Base):
    """
    使用者本機的執行代理（local runner）。task.runner_id 指到這裡，
    代表這個 task 不會派給共用的 Celery worker，而是等對應的本機 agent
    輪詢 /runner/tasks/next 來認領、在使用者自己的機器上執行。
    """
    __tablename__ = "runners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # 高熵亂數 token 的 SHA-256（不是密碼，用可直接查表的雜湊即可，不需要 bcrypt）
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
