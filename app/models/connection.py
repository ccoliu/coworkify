import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import UUID, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Connection(Base):
    """
    一組使用者自己的密鑰（GitHub token、Discord webhook……），workflow 步驟用
    {{connections.<name>}} 引用，執行當下才在 worker 裡解密代換。

    值只以加密後的形式存在這裡（見 app/core/connection_crypto.py），API 寫進去之後
    就不會再回傳。名稱在同一個使用者底下唯一。
    """
    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("created_by", "name", name="uq_connections_owner_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
