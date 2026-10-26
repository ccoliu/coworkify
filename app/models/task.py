import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import UUID, String, DateTime, JSON, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 非 None 代表這個 task 被「刪除」了：軟刪除，資料留著（給 workflow 詳情頁、
    # TaskLog 稽核紀錄用），只是從一般查詢（列表、單筆查詢）隱藏起來。
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 被 worker 認領成 RUNNING 的時間（UTC）。recover_stale_tasks 靠它找出「worker 已經
    # 死掉、卻永遠停在 RUNNING」的 task。只有 RUNNING 時有值，結束（成功或失敗）就清掉。
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 擁有者：只有建立它的使用者（workflow 裡的 task 跟著 workflow）看得到、改得了。API 對別人的資源一律回 404。
    # 舊資料由 2026_10_26_owners.sql 回填。
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
