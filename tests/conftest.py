# ---------------------------------------------------
# Coworkify — shared pytest fixtures
#
# `db` gives executor tests a real Postgres session against a separate
# `<POSTGRES_DB>_test` database on the same server as the dev stack (the
# docker-compose postgres, reached from the host via .env's DATABASE_URL).
# Postgres rather than SQLite on purpose: the executor leans on JSON columns
# and UUID-typed IN queries whose behaviour differs between the two.
#
# Override with TEST_DATABASE_URL to point somewhere else. Tests that don't
# request `db` never touch the database.
# ---------------------------------------------------

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  註冊所有 model，create_all 才建得到全部的表
from app.db import Base

def _test_database_url():
    if os.getenv("TEST_DATABASE_URL"):
        return make_url(os.environ["TEST_DATABASE_URL"])
    url = make_url(os.environ["DATABASE_URL"])
    return url.set(database=f"{url.database}_test")

@pytest.fixture(scope="session")
def db_engine():
    url = _test_database_url()

    # CREATE DATABASE 不能在交易裡跑，要連到 server 預設的 postgres 庫、開 AUTOCOMMIT
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE {url.database}'))
    except Exception as exc:
        # 印出原始錯誤：「連不上」跟「密碼錯」的處理方式完全不同
        reason = str(exc).strip().splitlines()[0]
        pytest.skip(f"Can't CREATE DATABASE on test Postgres, skipping DB tests: {reason}")
    finally:
        admin.dispose()
    
    engine = create_engine(url)
    # 測試庫每次從 model 重建，不必跟著 scripts/migrations 手動 ALTER
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture
def db(db_engine):
    # executor 內部到處 db.commit()，沒辦法用「包一個交易最後 rollback」隔離，
    # 改成每個測試結束後把所有表清空
    session = sessionmaker(bind=db_engine, autoflush=False)()
    yield session
    session.close()
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))

# --- API 測試用 ----------------------------------------------------------------

class _FakePipeline:
    """RateLimiter 只用到 pipeline 的 zremrangebyscore/zcard/zadd/expire/execute。"""

    def __init__(self, redis):
        self._redis = redis
    
    def __getattr__(self, name):
        return lambda *args, **kwargs: self
    
    async def execute(self):
        # 第一次 execute 的回傳是 [移除筆數, 視窗內請求數]，第二次的內容 RateLimiter 不看
        return [0, self._redis.requests_in_window]

class FakeRedis:
    """取代限流器的 Redis：CI 沒有 Redis，而限流不是這些測試要驗的東西。"""

    def __init__(self):
        self.requests_in_window = 0
    
    def pipeline(self):
        return _FakePipeline(self)


@pytest.fixture
def client(db, db_engine, monkeypatch):
    """
    打真正的 FastAPI app，資料庫換成測試庫；Celery 派送與 Redis 推播換成記錄器。
    依賴 db fixture，所以每個測試結束後一樣會清空所有表。

    不用 `with TestClient(...)`：那會觸發 lifespan，對 .env 裡的開發用資料庫跑 create_all。
    """
    from fastapi.testclient import TestClient

    import app.api.tasks as tasks_api
    from app.core import rate_limit
    from app.db import get_db
    from app.main import app as fastapi_app
    from app.tasks import executor

    TestSession = sessionmaker(bind=db_engine, autoflush=False)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    fake_redis = FakeRedis()
    monkeypatch.setattr(rate_limit, "redis_client", fake_redis)

    dispatched: list = []
    scheduled: list = []

    def record_dispatch(task, countdown=None):
        dispatched.append(task.id)

    monkeypatch.setattr(executor, "dispatch_task", record_dispatch)
    monkeypatch.setattr(tasks_api, "dispatch_task", record_dispatch)
    monkeypatch.setattr(executor.execute_task, "apply_async", lambda args, **options: scheduled.append((args, options)))
    monkeypatch.setattr(executor, "notify_status_change", lambda *a, **kw: None)

    test_client = TestClient(fastapi_app)
    test_client.dispatched = dispatched
    test_client.scheduled = scheduled
    test_client.fake_redis = fake_redis

    yield test_client
    fastapi_app.dependency_overrides.clear()

@pytest.fixture
def auth(client):
    """註冊一個使用者，回傳帶 JWT 的 headers。"""
    res = client.post("/auth/register", json={"username": "alice", "password": "correct-horse"})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}




@pytest.fixture
def other_auth(client):
    """第二個使用者，用來測「看不到、改不了別人的東西」。"""
    res = client.post("/auth/register", json={"username": "mallory", "password": "correct-horse"})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
