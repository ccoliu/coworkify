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
    


