from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import engine, Base
import app.models
from app.api.tasks import router as tasks_router
from app.api.ws import router as ws_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時自動在 PostgreSQL 建立所有尚未存在的 Table
    Base.metadata.create_all(bind=engine)
    yield
    # 關閉時可在此執行資源釋放動作

app = FastAPI(
    title="Coworkify - 分散式任務排程平台", # 應用程式名稱
    version="0.1.0", # 應用程式版本
    lifespan=lifespan # FastAPI 生命周期管理
)

app.include_router(tasks_router)
app.include_router(ws_router)

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Coworkify is running."}