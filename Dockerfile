FROM python:3.11-slim

WORKDIR /app

# 安裝 PostgreSQL 連線需要的系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 預設啟動 FastAPI 服務 和 Celery Worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]