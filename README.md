# ⚡ Coworkify - Distributed Task Scheduling & Execution Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg?style=flat&logo=PostgreSQL&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D.svg?style=flat&logo=Redis&logoColor=white)](https://redis.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=Python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat&logo=Docker&logoColor=white)](https://www.docker.com/)

**Coworkify** 是一個輕量、高效且具備彈性的分散式任務排程與管理平台（架構靈感源自 Apache Airflow 與 Celery）。使用者與微服務可以透過 RESTful API 定義、排程、追蹤與監控各類非同步任務。

---

## 🌟 核心特色 (Key Features)

- 🔄 **完整的任務生命週期管理**：支援 `pending` ➔ `running` ➔ `success` / `failed` / `retrying` / `cancelled` 狀態機流轉。
- ⚡ **高性能非同步架構**：以 FastAPI 作為核心 API 閘道，結合 Redis 實現低延遲訊息佇列 (Message Broker)。
- 🎯 **任務優先級調度 (Priority Queue)**：支援任務加權插隊，優先處理高優先級核心任務。
- ⏱️ **排程與延遲執行**：支援立即執行、指定時間執行與定時排程。
- 🛡️ **彈性重試機制**：內建自訂重試次數 (`max_retries`) 與退避策略 (Backoff Strategy)。
- 📊 **端到端可觀測性**：紀錄任務執行耗時、錯誤堆疊 (Traceback) 與工作節點狀態。

---

## 🏗️ 系統架構 (System Architecture)

```mermaid
flowchart TD
    Client[客戶端 / 前端 Client] -->|HTTP REST API| API[FastAPI API Server]
    API -->|1. 寫入任務中繼資料| DB[(PostgreSQL Database)]
    API -->|2. 推送任務至佇列| Redis[(Redis Broker)]
    Worker[Celery Background Workers] -->|3. 消費任務| Redis
    Worker -->|4. 更新狀態與日誌| DB
```

## 使用方式 

## 配置需求
- Python 3.11 or above
- Docker

### 啟動服務
```bash
docker-compose up -d
```

### 啟動 FastAPI
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 啟動 Celery Worker
```bash
uvicorn app.worker:celery --loglevel=info
```