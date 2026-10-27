# ---------------------------------------------------
# Coworkify — the API's connection pool must cover its thread pool
#
# A request takes a connection in get_current_user (run in a worker thread)
# and keeps it while it queues for another thread to run the endpoint. If
# the pool is smaller than the thread pool, requests holding connections
# wait for threads while requests holding threads wait for connections, and
# everything stalls until pool_timeout. The load test hit exactly this when
# the pool was shrunk to 10 + 10: 5 RPS and a wall of 500s at 150 users.
# ---------------------------------------------------

from __future__ import annotations

import os

import anyio.to_thread
import pytest

from app.db import engine

@pytest.mark.skipif(
    "DB_POOL_SIZE" in os.environ or "DB_MAX_OVERFLOW" in os.environ,
    reason="checks the API defaults; worker processes override them on purpose"
)

async def test_the_api_pool_is_not_smaller_than_its_thread_pool():
    threads = anyio.to_thread.current_default_thread_limiter().total_tokens
    connections = engine.pool.size() + engine.pool._max_overflow

    assert connections > threads
