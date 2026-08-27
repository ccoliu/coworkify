import os
import asyncio
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
router = APIRouter(tags=["WebSocket"])

@router.websocket("/ws/tasks")
async def websocket_tasks_endpoint(websocket: WebSocket):
    await websocket.accept()
    # 建立非同步 Redis 連線並訂閱頻道
    redis_sub = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_sub.pubsub()
    await pubsub.subscribe("task_updates")
    
    try:
        # 持續監聽 Redis 訊息並即時推送到 WebSocket
        async for message in pubsub.listen():
            if message['type'] == 'message':
                await websocket.send_text(message['data'])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe("task_updates")
        await redis_sub.close()

