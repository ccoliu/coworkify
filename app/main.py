from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from app.db import engine, Base
import app.models
from app.api.tasks import router as tasks_router
from app.api.ws import router as ws_router
from app.api.workflows import router as workflows_router
from app.api.auth import router as auth_router
from app.api.schedule import router as schedule_router
from fastapi.middleware.cors import CORSMiddleware
from app.api.definitions import router as definitions_router
from app.core.log_redaction import install_token_redaction
from app.core.concurrency import InFlightLimitMiddleware
from app.api.connections import router as connections_router

# /ws/tasks?token=<JWT>：uvicorn 會把完整網址寫進 log，先遮掉 token 再說
install_token_redaction()

# 任意挑的一個常數，只用來當 Postgres advisory lock 的鑰匙
_SCHEMA_LOCK_KEY = 7_272_026


def create_tables() -> None:
    """
    啟動時建立所有尚未存在的 Table。

    uvicorn --workers N 會讓每個 process 各跑一次 lifespan。create_all 是「先查表在不在、
    不在才建」，空資料庫上兩個 process 會同時查到「不在」、同時建，後到的撞上
    duplicate key——uvicorn 看到任何一個 child 啟動失敗就把整個服務停掉。
    用 transaction 層級的 advisory lock 讓它們排隊：第一個建完、commit 放鎖，
    後面的進來時表已經在了，create_all 什麼都不做。
    """
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SCHEMA_LOCK_KEY})
        Base.metadata.create_all(bind=conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield
    # 關閉時可在此執行資源釋放動作

app = FastAPI(
    title="Coworkify - 分散式任務排程平台", # 應用程式名稱
    version="0.1.0", # 應用程式版本
    lifespan=lifespan # FastAPI 生命周期管理
)

# 先加的在內層：in-flight 上限包在 CORS 裡面，被擋著排隊的請求也照樣有 CORS header
app.add_middleware(InFlightLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(tasks_router)
app.include_router(ws_router)
app.include_router(workflows_router)
app.include_router(auth_router)
app.include_router(schedule_router)
app.include_router(definitions_router)
app.include_router(connections_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Coworkify is running."}