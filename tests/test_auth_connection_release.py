# ---------------------------------------------------
# Coworkify — authenticating a request must not pin a database connection
#
# get_current_user runs in a worker thread; the request then queues for
# another thread to run the endpoint. If the session still holds its
# connection during that wait, the pool fills up with requests that are
# only waiting — at 150 concurrent users the pool's 50 connections ran out
# and requests failed with QueuePool timeouts after 30 seconds.
# ---------------------------------------------------

from __future__ import annotations

from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, get_current_user, hash_password
from app.models.user import User


def test_the_connection_goes_back_to_the_pool_after_authentication(db, db_engine):
    user = User(username="alice", password_hash=hash_password("correct-horse"))
    db.add(user)
    db.commit()
    token = create_access_token(user.id)

    session = sessionmaker(bind=db_engine)()
    try:
        current = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), session)

        assert not session.in_transaction()           # 連線已經還回 pool
        assert current.id == user.id                   # 欄位照樣讀得到，不必再查資料庫
        assert current.username == "alice"
    finally:
        session.close()
