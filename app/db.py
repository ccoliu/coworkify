import os
from pathlib import Path
import sqlalchemy
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

engine = sqlalchemy.create_engine(
    DATABASE_URL,
    pool_size=50, #基礎連線數
    max_overflow=50, #最大突發額外連線數
    pool_timeout=30, #連線等待超時
    pool_pre_ping=True #檢查連線是否有效
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()