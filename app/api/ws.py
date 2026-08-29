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
        while True:
            # 設定 1 秒超時，避免阻塞
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            # 處理接收到的訊息
            if message:
                # 發送訊息至 WebSocket 客戶端
                await websocket.send_text(message['data'])
            # 避免 CPU 使用率過高
            await asyncio.sleep(0.1) 
            
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await pubsub.unsubscribe("task_updates")
        await pubsub.close()
        await redis_sub.close()

