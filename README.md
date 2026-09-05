# Coworkify - Distributed Task Scheduling & Execution Platform

[English](README.en.md) | 繁體中文

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg?style=flat&logo=PostgreSQL&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D.svg?style=flat&logo=Redis&logoColor=white)](https://redis.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=Python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat&logo=React&logoColor=white)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat&logo=Docker&logoColor=white)](https://www.docker.com/)

**Coworkify** 是一個輕量、高效且具備彈性的分散式任務排程與管理平台（架構靈感源自 Apache Airflow 與 Celery）。使用者與微服務可以透過 RESTful API 定義、排程、追蹤與監控各類非同步任務，並支援多任務串接成 DAG workflow，使用Redis + Postgres + Celery 組成，預計可承受每日 10M+ 請求。

![alt text](<coworkify.png>)
---

## 核心特色 (Key Features)

- **完整的任務生命週期管理**：支援 `pending` ➔ `running` ➔ `success` / `failed` / `retrying` / `cancelled` 狀態機流轉。
- **高性能非同步架構**：以 FastAPI 作為核心 API 閘道，結合 Redis 實現低延遲訊息佇列 (Message Broker)。
- **任務優先級調度 (Priority Queue)**：支援任務加權插隊，優先處理高優先級核心任務。
- **排程與延遲執行**：支援立即執行、指定時間執行與定時排程。
- **彈性重試機制**：內建自訂重試次數 (`max_retries`) 與指數退避策略 (Exponential Backoff)。
- **DAG Workflow 編排**：支援多個任務依照依賴關係串接執行（`task1 → task2 → task3`，含分支/合併），單一節點失敗會自動連鎖取消下游節點。
- **Cron 週期性排程**：workflow 可綁定標準 5 欄位 cron 表達式（例如「每天 9 點」），由 Celery Beat 定期檢查、到點自動建立並派送整組 workflow，時區與應用程式設定一致。
- **Redis 滑動窗口限流**：每個登入使用者獨立計算請求速率，防止單一來源打爆系統。
- **即時任務狀態推播**：透過 WebSocket 與 Redis Pub/Sub 實現任務狀態即時推播，前端無需輪詢。
- **帳號登入認證**：註冊／登入以 bcrypt 雜湊密碼、JWT 簽發 session token，前端自助註冊帳號即可使用。
- **即時 Ops 儀表板**：React 前端提供任務佇列深度、吞吐量、錯誤率的即時可視化，並有可視化 DAG 流程圖檢視 workflow 執行進度。

---



## 內建支援的任務類型 (Supported Task Handlers)

| 任務類型 (task_type) | 說明 |
| :--- | :--- |
| `echo` | 簡單回聲任務，用於測試系統連通性 |
| `heavy_computation` | 模擬耗時運算任務，可指定執行時間 |
| `flaky_task` | 模擬可能失敗的任務，用於測試自動重試機制 |

---

## 快速開始 (Quick Start)

### 配置需求
- Docker / Docker Compose

### 1. 設定環境變數
複製一份 `.env`（範例參考 `docker-compose.yml` 所需的變數：`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`JWT_SECRET` 等），改成自己的值。`JWT_SECRET` 用來簽發登入 token，建議用 `python -c "import secrets; print(secrets.token_hex(32))"` 產生一組隨機字串。

### 2. 一鍵啟動全部服務
```bash
docker-compose up -d --build
```
會啟動：PostgreSQL、Redis、FastAPI API、Celery Worker、Celery Beat（排程檢查）、React 前端。

- 前端 Dashboard: http://localhost:5173
- API 文件 (Swagger UI): http://localhost:8000/docs
- 健康檢查: http://localhost:8000/health

### 3. 啟動 Locust 壓力測試
```bash
locust -f tests/locustfile.py --host http://localhost:8000
```

---

## 主要 API 端點

### Auth
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/auth/register` | 註冊新帳號（username + password），成功後直接回傳 JWT |
| `POST` | `/auth/login` | 登入既有帳號，回傳 JWT |
| `GET` | `/auth/me` | 查詢目前登入使用者資訊，用來驗證 token 是否還有效 |

### Tasks
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/tasks/` | 建立並自動派發任務 (支援立即或指定 `scheduled_at` 排程) |
| `GET` | `/tasks/` | 分頁查詢任務列表 (支援狀態/類型篩選與優先級排序) |
| `GET` | `/tasks/{task_id}` | 查詢單一任務詳細狀態與回傳結果 |
| `DELETE` | `/tasks/{task_id}` | 刪除指定任務 |

### Workflows (DAG)
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/workflows/` | 建立一組 DAG workflow，自動派送沒有依賴的根節點任務 |
| `GET` | `/workflows/{workflow_id}` | 查詢 workflow 整體狀態與每個節點對應任務的即時狀態 |

一個 3 節點線性 workflow 範例：
```json
POST /workflows/
{
  "name": "demo-pipeline",
  "steps": [
    { "key": "t1", "name": "step1", "task_type": "echo", "payload": {"message": "step1"}, "depends_on": [] },
    { "key": "t2", "name": "step2", "task_type": "echo", "payload": {"message": "step2"}, "depends_on": ["t1"] },
    { "key": "t3", "name": "step3", "task_type": "echo", "payload": {"message": "step3"}, "depends_on": ["t2"] }
  ]
}
```
`depends_on` 可以填多個 key，支援分支與合併（真正的 DAG，不只是線性鏈）；任一節點徹底失敗（重試耗盡）時，所有下游節點會被自動標記為 `cancelled`，整個 workflow 標記為 `failed`。

### Schedules（週期性排程）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/schedules/` | 建立一個綁定 cron 表達式的週期性 workflow（steps 定義同 `/workflows/`） |
| `GET` | `/schedules/` | 列出所有排程 |
| `GET` | `/schedules/{schedule_id}` | 查詢單一排程 |
| `PATCH` | `/schedules/{schedule_id}` | 更新排程內容、cron 或啟用狀態 |
| `DELETE` | `/schedules/{schedule_id}` | 刪除排程 |

Celery Beat 每分鐘檢查一次所有 `enabled=true` 的排程，`next_run_at` 到期就依 `steps` 建立一份新的 workflow 並派送根節點，再依 cron 表達式計算下一次執行時間。cron 以應用程式設定的時區（`Asia/Taipei`）解讀，跟 `next_run_at` 的顯示、比較邏輯保持一致。

### 其他
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `GET` | `/health` | API 伺服器健康檢查 |
| `WS` | `/ws/tasks` | WebSocket 即時任務狀態推播 (Redis Pub/Sub) |

`/tasks`、`/workflows`、`/schedules` 底下所有端點都需要先透過 `/auth/register` 或 `/auth/login` 取得 JWT，帶在 `Authorization: Bearer <token>` header 裡才能存取，並依登入身份受 Redis 滑動窗口限流保護。

---

## 壓力測試報告 (Benchmark Results)

使用 **Locust** 在 150 併發使用者、2 分鐘測試窗口下進行負載測試，模擬多用戶並發讀寫請求（包含資料庫查詢、任務建立與 Redis 佇列派發），資料庫在測試前已清空：
- **總測試請求數**：23,310 Requests
- **失敗率**：**0.06% (14 Failures，皆為 Windows loopback 網路層 `ConnectionResetError`，非應用層錯誤)**
- **系統吞吐量 (Throughput)**：**194.5 RPS**
- **平均延遲 (Average Latency)**：**443 ms**
- **P95 延遲**：**820 ms**
- **中位數延遲 (Median)**：**410 ms**

| API 端點 | 請求類型 | 平均延遲 (ms) | 吞吐量 (RPS) | 失敗率 |
| :--- | :--- | :--- | :--- | :--- |
| `GET /health` | 健康檢查 | 115 ms | 32.7 RPS | 0.05% |
| `GET /tasks` | 資料庫分頁查詢 | 502 ms | 97.2 RPS | 0.08% |
| `POST /tasks` | 任務建立 + 佇列派發 | 520 ms | 64.5 RPS | 0.04% |

> 延遲比早期版本高，原因是這次測試是在修正 API 限流器的 event-loop 阻塞 bug**之後**，用真實通過驗證、實際打到資料庫的請求測出來的乾淨數字；先前 288 RPS / 38.9ms 那組數字量到的其實大多是驗證失敗、幾乎不碰資料庫的快速拒絕請求，兩者不是同一件事，不能直接比較。目前的瓶頸研判在於 `/tasks` 端點是同步 (`def`，非 `async def`) SQLAlchemy 呼叫，FastAPI 會丟進 thread pool 執行，高併發下容易排隊；之後若要繼續壓榨吞吐量，可以考慮把 DB 層換成 async（`asyncpg` + SQLAlchemy async session）。
>
> 這組數字是在認證機制從 API Key 換成 JWT 帳號登入**之前**測的（驗證身份的檢查方式改變了，但都是 O(1) 的查詢/解碼，預期不會是主要瓶頸），之後重新量測時一併更新這個表格。

### Workflow 建立吞吐量

同一輪 150 併發測試裡加入 `POST /workflows`（每次建立 3 節點線性 pipeline）：

| API 端點 | 請求類型 | 平均延遲 (ms) | 吞吐量 (RPS) | 失敗率 |
| :--- | :--- | :--- | :--- | :--- |
| `POST /workflows` | 建立 3 節點 workflow + 派送根節點 | 578 ms | 24.6 RPS | 0.20% |

測試期間總共建立了 2,941 個 workflow，事後全數確認**完整跑完、依序執行、無一卡死或錯誤**（`advance_workflow` 的鏈式派送邏輯在高併發下是穩的）。但要注意：workflow 任務跟一般 `POST /tasks` 測試流量共用同一個 `concurrency=4` 的 Celery worker pool，尤其 `heavy_computation` 這種會真的 `sleep(1)` 秒的任務一多，workflow 鏈的完成時間會被排擠拉長——這是資源共用造成的排隊延遲，不是邏輯問題。之後如果要單獨測 workflow 的延遲，建議跟其他任務類型的負載分開跑，或幫 workflow 開一條獨立的 Celery queue。

---

## 前端開發

React + TypeScript + Tailwind SPA，細節見 [frontend/README.md](frontend/README.md)。`docker-compose up` 起來後 Vite dev server 會自動 proxy `/api` 跟 `/ws` 到後端，不需要另外設 CORS。

- **登入頁**：支援註冊新帳號或用既有帳號登入，登入後 JWT 存在瀏覽器 localStorage，重新整理不用再登入一次。
- **Tasks 頁**：任務列表、篩選、建立單一任務，狀態透過 WebSocket 即時更新。
- **Workflows 頁**：列出所有建立過的 workflow，可用多步驟表單建立新的 DAG（每個步驟可勾選要依賴哪些前面的步驟、或設定 `for_each` 動態展開來源），點進去可看拓樸分層畫出來的管線圖，每個節點即時顯示執行狀態。
- **Schedules 頁**：管理週期性 workflow，用同一套步驟編輯器搭配 cron 表達式輸入（含常用預設如「每天 9:00」），顯示下一次/上一次執行時間，可隨時啟用/停用或編輯。
- **Ops 頁**：佇列深度、吞吐量走勢圖、錯誤率等即時監控指標。
