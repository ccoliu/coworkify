from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConnectionCreate(BaseModel):
    # 名稱會出現在 {{connections.<name>}} 裡，規則跟 step key 一樣
    name: str = Field(..., pattern=r"^[a-zA-Z0-9_]+$", max_length=100)
    value: str = Field(..., min_length=1, max_length=4000)
    description: Optional[str] = Field(None, max_length=500)


class ConnectionUpdate(BaseModel):
    """換一個新的值（例如 token 過期）或改說明。名稱不能改：已經有步驟用名稱引用它。"""
    value: Optional[str] = Field(None, min_length=1, max_length=4000)
    description: Optional[str] = Field(None, max_length=500)


class ConnectionResponse(BaseModel):
    """刻意沒有 value：密鑰寫進去之後就不會再從 API 出來。"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
