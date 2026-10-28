import asyncio
import os

# 同一個 API process 同時「正在處理」的 HTTP 請求上限，多出來的在 event loop 裡排隊。
#
# 一個同步的請求會在 thread pool 裡跑好幾段：驗證身分、endpoint、把 ORM 物件序列化成回應。
# 資料庫連線會跨過這幾段一直被占著；同時處理的請求一旦比連線池多，就會出現「拿著連線的
# 請求等 thread、占著 thread 的請求等連線」——壓測 1 個 process、300 人時整個卡死，
# CPU 0%、等滿 pool_timeout 才變成 500。
#
# 讓處理中的請求不超過連線池大小，每個請求就一定拿得到連線，這種互卡不可能發生；
# 排隊的請求還沒碰資料庫，只是多等一下。預設 40 = AnyIO thread pool 的大小，也小於
# api 的連線池 50（見 app/db.py；tests/test_db_pool.py 會檢查這兩者的關係）。
MAX_IN_FLIGHT = int(os.getenv("API_MAX_IN_FLIGHT", "40"))


class InFlightLimitMiddleware:
    """純 ASGI middleware：HTTP 請求拿到名額才往下走；WebSocket 是長連線，不佔名額。"""

    def __init__(self, app, limit: int = MAX_IN_FLIGHT):
        self.app = app
        self.limit = limit
        self._slots: asyncio.Semaphore | None = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # 在第一個請求時才建立：要綁在 uvicorn 實際跑的那個 event loop 上
        if self._slots is None:
            self._slots = asyncio.Semaphore(self.limit)
        async with self._slots:
            await self.app(scope, receive, send)
