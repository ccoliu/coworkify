import os
import asyncio
import json
from uuid import UUID

import jwt
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from dotenv import load_dotenv
from pathlib import Path

from app.core.security import JWT_ALGORITHM, JWT_SECRET
from app.db import SessionLocal
from app.models.task import Task

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
router = APIRouter(tags=["WebSocket"])

# 每條連線記住看過的 task 擁有者，同一個 task 的後續事件不必再查 DB
_OWNER_CACHE_LIMIT = 2000


def _user_id_from_token(token: str | None) -> UUID | None:
    """瀏覽器的 WebSocket 不能自訂 header，JWT 走 query string（?token=...）。"""
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def _task_owner(task_id: str):
    with SessionLocal() as db:
        task = db.get(Task, UUID(task_id))
        return task.created_by if task else None


@router.websocket("/ws/tasks")
async def websocket_tasks_endpoint(websocket: WebSocket):
    user_id = _user_id_from_token(websocket.query_params.get("token"))
    if user_id is None:
        # 1008 = policy violation：前端看到就知道要重新登入，不是網路問題
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    # 建立非同步 Redis 連線並訂閱頻道
    redis_sub = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_sub.pubsub()
    await pubsub.subscribe("task_updates")
    owners: dict[str, UUID | None] = {}

    try:
        while True:
            # 僅在沒有訊息時才休眠 (與 timeout 類似，但更精準)
            message = await pubsub.get_message(ignore_subscribe_messages=True)

            if not message:
                # 避免 CPU 使用率過高
                await asyncio.sleep(0.1)
                continue

            # 頻道裡是所有人的事件（含 result），只轉送這個使用者自己的 task
            try:
                task_id = json.loads(message["data"])["task_id"]
            except (ValueError, KeyError, TypeError):
                continue
            if task_id not in owners:
                if len(owners) >= _OWNER_CACHE_LIMIT:
                    owners.clear()
                owners[task_id] = await asyncio.to_thread(_task_owner, task_id)
            if owners[task_id] == user_id:
                await websocket.send_text(message["data"])
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await pubsub.unsubscribe("task_updates")
        await pubsub.close()
        await redis_sub.close()
