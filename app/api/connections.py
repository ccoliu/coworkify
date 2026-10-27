from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.connection_crypto import ConnectionsKeyMissing, encrypt
from app.core.ownership import get_owned_or_404
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.db import get_db
from app.models.connection import Connection
from app.models.user import User
from app.schemas.connection import ConnectionCreate, ConnectionResponse, ConnectionUpdate

router = APIRouter(
    prefix="/connections",
    tags=["Connections"],
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5000, seconds=1))],
)


def _encrypt_or_503(value: str) -> str:
    try:
        return encrypt(value)
    except ConnectionsKeyMissing as exc:
        # 伺服器設定問題，不是請求的錯：明講缺什麼，而不是丟一個看不懂的 500
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("/", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    taken = db.scalars(
        select(Connection.id).where(Connection.created_by == current_user.id, Connection.name == payload.name)
    ).first()
    if taken:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"You already have a connection named '{payload.name}'")

    connection = Connection(
        name=payload.name,
        description=payload.description,
        encrypted_value=_encrypt_or_503(payload.value),
        created_by=current_user.id,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.get("/", response_model=List[ConnectionResponse])
def list_connections(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.scalars(
        select(Connection).where(Connection.created_by == current_user.id).order_by(Connection.name)
    ).all()


@router.patch("/{connection_id}", response_model=ConnectionResponse)
def update_connection(
    connection_id: UUID,
    payload: ConnectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = get_owned_or_404(db, Connection, connection_id, current_user, "Connection not found")
    if payload.value is not None:
        connection.encrypted_value = _encrypt_or_503(payload.value)
    if payload.description is not None:
        connection.description = payload.description
    db.commit()
    db.refresh(connection)
    return connection


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = get_owned_or_404(db, Connection, connection_id, current_user, "Connection not found")
    db.delete(connection)
    db.commit()
    return None
