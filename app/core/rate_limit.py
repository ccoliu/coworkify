import time
import uuid
import os
import redis
from fastapi import Request, HTTPException, status
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

class RateLimiter:
    def __init__(self, times: int = 5, seconds: int = 10):
        """
        :param times: 窗口內允許的最大請求次數
        :params seconds: 滑動窗口大小(秒)
        """

        self.times = times
        self.seconds = seconds

    async def __call__(self, request: Request):
        # 優先以 API Key 作為識別對象，若無則使用 Client IP
        client_key = request.headers.get("X-API-Key") or request.client.host
        route_path = request.url.path 
        rate_key = f"ratelimit:{client_key}:{route_path}"

        now = time.time()
        window_start = now - self.seconds
        req_id = str(uuid.uuid4())

        # Redis Pipelining 批次執行
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(rate_key, 0, window_start) # 移除視窗外的舊請求
        pipe.zcard(rate_key) # 計算當前請求次數
        _, current_requests = pipe.execute()

        if current_requests >= self.times:
            retry_after = int(self.seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too Many Request. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

        pipe = redis_client.pipeline()
        pipe.zadd(rate_key, {req_id: now})
        pipe.expire(rate_key, self.seconds * 2) # 到期自動刪除
        pipe.execute()

        return
    