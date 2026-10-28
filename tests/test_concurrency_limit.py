# ---------------------------------------------------
# Coworkify — at most MAX_IN_FLIGHT requests are processed at once
#
# A request holds its database connection across several thread-pool hops
# (auth, endpoint, response serialisation). With more requests in progress
# than pool connections, those holding connections wait for threads while
# those holding threads wait for connections; the load test saw one API
# process at 300 users stall at 0% CPU until every request timed out.
# Queueing requests before they touch the database rules that out.
# ---------------------------------------------------

from __future__ import annotations

import asyncio

from app.core.concurrency import MAX_IN_FLIGHT, InFlightLimitMiddleware
from app.db import engine


def make_app():
    state = {"now": 0, "peak": 0}

    async def app(scope, receive, send):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1

    return app, state


async def test_requests_beyond_the_limit_wait_instead_of_running():
    app, state = make_app()
    limited = InFlightLimitMiddleware(app, limit=3)

    await asyncio.gather(*(limited({"type": "http"}, None, None) for _ in range(20)))

    assert state["peak"] == 3  # 20 個都做完了，但同時最多 3 個


async def test_websockets_do_not_take_a_slot():
    app, state = make_app()
    limited = InFlightLimitMiddleware(app, limit=1)

    await asyncio.gather(*(limited({"type": "websocket"}, None, None) for _ in range(5)))

    assert state["peak"] == 5


def test_the_limit_fits_inside_the_connection_pool():
    # 每個處理中的請求最多拿一條連線；名額比池子大就又可能互卡
    assert MAX_IN_FLIGHT <= engine.pool.size() + engine.pool._max_overflow
