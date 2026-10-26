from typing import TypeVar
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User

T = TypeVar("T")


def get_owned_or_404(db: Session, model: type[T], obj_id: UUID, user: User, detail: str) -> T:
    """
    取一筆屬於 user 的資源。不存在和「存在但不是你的」一律回 404——
    回 403 等於告訴對方這個 id 確實存在。
    """
    obj = db.get(model, obj_id)
    if obj is None or obj.created_by != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj
