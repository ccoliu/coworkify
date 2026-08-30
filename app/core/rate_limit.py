import time
import uuid
import os
import redis.asyncio as redis
from fastapi import Request, HTTPException, status, Depends
from dotenv import load_dotenv
from pathlib import Path
from app.core.security import get_current_user
from app.models.user import User

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

    async def __call__(self, request: Request, current_user: User = Depends(get_current_user)):
        # 優先以 API Key 作為識別對象，若無則使用 Client IP
        rate_key = f"ratelimit:{current_user.id}:{request.url.path}"

        now = time.time()
        window_start = now - self.seconds
        req_id = str(uuid.uuid4())

        # Redis Pipelining 批次執行
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(rate_key, 0, window_start) # 移除視窗外的舊請求
        pipe.zcard(rate_key) # 計算當前請求次數
        _, current_requests = await pipe.execute()

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
        await pipe.execute()

        return
    