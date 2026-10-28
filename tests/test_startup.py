# ---------------------------------------------------
# Coworkify — several API processes starting on an empty database
#
# `uvicorn --workers N` runs the lifespan once per process, and each one
# creates any missing tables. Without coordination, two processes both see
# "table missing", both CREATE it, and the loser crashes with a duplicate
# key — which makes uvicorn stop the whole server. The load test hit this
# on its first multi-process run.
# ---------------------------------------------------

from __future__ import annotations

import threading

from sqlalchemy import create_engine, inspect, text

import app.main
from app.db import Base


def test_concurrent_startups_on_an_empty_database_all_succeed(db_engine, monkeypatch):
    # 拿一個空的 schema 給這個測試用，不碰其他測試共用的資料表
    with db_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS startup_race CASCADE"))
        conn.execute(text("CREATE SCHEMA startup_race"))
    engine = create_engine(
        db_engine.url, pool_size=8, connect_args={"options": "-csearch_path=startup_race"}
    )
    monkeypatch.setattr(app.main, "engine", engine)

    start = threading.Barrier(6)
    errors = []

    def boot():
        start.wait()  # 六個「process」同時開始建表
        try:
            app.main.create_tables()
        except Exception as exc:  # noqa: BLE001 — 要收集的正是任何一種失敗
            errors.append(exc)

    threads = [threading.Thread(target=boot) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert errors == []
        tables = set(inspect(engine).get_table_names(schema="startup_race"))
        assert tables == set(Base.metadata.tables)
    finally:
        engine.dispose()
        with db_engine.begin() as conn:
            conn.execute(text("DROP SCHEMA startup_race CASCADE"))
