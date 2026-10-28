import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

JWT_SECRET = os.getenv("JWT_SECRET", "changeme_jwt_secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # 驗完身分就把連線還回 pool。這個 dependency 跑在 thread 裡，但請求接著還要排隊等另一條
    # thread 跑 endpoint；不還的話，連線會被「排隊中、什麼都沒做」的請求一路占到請求結束——
    # event loop 能同時收的請求遠多於 pool 的 50 條，壓測 150 人時就是這樣把 pool 占滿、
    # 等滿 30 秒變成 500。先 expunge 再 rollback：user 的欄位已經載入，脫離 session 之後
    # 照樣能讀（各 endpoint 只用到 current_user.id），rollback 結束交易、連線就回到 pool；
    # endpoint 真的要查資料時，同一個 session 會再借一條。
    db.expunge(user)
    db.rollback()
    return user
