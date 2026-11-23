import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import UUID, Boolean, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TriggerKind:
    WEBHOOK = "webhook"
    WORKFLOW = "workflow"


class WorkflowTrigger(Base):
    """
    觸發器：某件事發生時，用 definition_id 這條產線建一個 run。兩種：

    - webhook：外部系統打 POST /hooks/{id}，靠 secret 驗證，不需要使用者的 JWT。
      secret 用 CONNECTIONS_KEY 加密存放，不是雜湊：驗 GitHub 的 X-Hub-Signature-256
      要拿原文算 HMAC，雜湊過就算不出來了。API 只在建立和換新時回傳一次原文。
    - workflow：source_definition_id 的某次 run 結束（成功／失敗／都算，見 on_status）時觸發。
      沒有 secret。

    input_mapping 和 filter 的路徑，webhook 是對 request body 取值；workflow 是對
    {"workflow_id", "status", "result", "input"} 取值（來源 run 的成品與輸入）。
    """
    __tablename__ = "workflow_triggers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default=TriggerKind.WEBHOOK)
    # 要啟動的產線。被刪掉，觸發器也沒有意義，跟排程一樣 ON DELETE CASCADE
    definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 只有 webhook 有
    encrypted_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    # 只有 workflow 有：看哪條產線的 run 結束。來源產線被刪掉，觸發器一起消失
    source_definition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=True, index=True, default=None,
    )
    # 只有 workflow 有："success" / "failed" / "any"
    on_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default=None)
    # run 輸入欄位 → 點分隔路徑，例如 {"sha": "head_commit.id"}、{"summary": "result.summarize"}。
    # 只有對應到的欄位會進 run，其他內容一律丟掉。
    input_mapping: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # 路徑 → 期望值，全部符合才建 run，例如 {"action": "opened"}。
    # 期望值是 list 代表「其中之一」。比對分型別：200 和 "200" 不同。
    filter: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # 跟排程一樣：last_triggered_at 只代表「真的建立了 run」，失敗記在 last_error，
    # 下一次成功就清掉
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
