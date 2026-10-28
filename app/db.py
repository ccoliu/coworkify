import os
from pathlib import Path
import sqlalchemy
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# 每個 process 都有自己的連線池：api 一個，Celery 的每個 worker 子 process 各一個，beat 也一個。
# 兩個限制都要滿足：
#   1. api 的池子不能比 AnyIO 的 thread pool（預設 40 條）小。一個請求會先在 thread 裡跑
#      get_current_user（拿走一條連線，拿到請求結束），再排隊等 thread 跑 endpoint；池子
#      比 thread 少時，拿著連線的請求等 thread、占著 thread 的請求等連線，互卡到
#      pool_timeout 才變成 500。
#   2. 所有 process 的上限加起來要小於 Postgres 的 max_connections（預設 100），否則新連線
#      直接被拒（FATAL: sorry, too many clients already）。
# 所以預設值給 api（20 + 30 = 50），worker / beat 一次只做一件事，在 docker-compose.yml
# 用 DB_POOL_SIZE / DB_MAX_OVERFLOW 調小。

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

engine = sqlalchemy.create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")), #基礎連線數
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "30")), #最大突發額外連線數
    pool_timeout=30, #連線等待超時
    pool_pre_ping=True #檢查連線是否有效
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

async def get_db():
    # 寫成 async：FastAPI 會把「同步」generator dependency 的收尾（db.close()、把連線還回
    # pool）也丟進 thread pool；尖峰時 thread 全被在等連線的請求占住，做完的請求就排不到
    # thread 還連線。async 的收尾在 event loop 上跑，不需要 thread，close() 的代價很小。
    # 這只拿掉其中一段排隊——單靠它擋不住互卡，真正保證的是 app/core/concurrency.py 的
    # 同時處理上限。session 本身照樣交給同步的 endpoint 在 thread 裡用。
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()