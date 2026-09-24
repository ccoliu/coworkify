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
- **視覺化 Workflow 編輯器**：在畫布上拖拉節點、拉線就是依賴關係，`condition` 節點的 `true` / `false` 出口直接對應 if/else 分支；前端即時鏡射後端的 DAG 驗證規則，問題標在節點上並擋住送出。
- **定義與執行分離**：workflow 是一條可重複使用的「產線」（`workflow_definitions`），每次執行是一筆帶著自己輸入的 run。run 會保留當下的 step 快照與定義版本號，所以之後修改定義不會改寫歷史紀錄。
- **表單化的輸入**：定義可以宣告 `input_schema`（欄位名稱、型別、預設值、是否必填），執行前由前端自動產生表單並驗證；填入的值從 `input` 節點進入整條 workflow。原料也可以來自網頁——`fetch_page` 抓指定網址並依 CSS selector 抽出結構化欄位。
- **型別安全的資料傳遞**：`python` 步驟以全域變數 `inputs` 取得所有上游結果（型別完整保留），`shell` 以 `$(./get_input <path>)` 取值，兩者都不經過字串插值，避免型別失真與指令注入。
- **明確的輸出**：跑完後所有終端節點的結果會收進 `workflows.result`，不用再逐一翻每個節點的執行紀錄。
- **重跑與續跑**：`POST /workflows/{id}/rerun` 用同一份快照與輸入建立新的一次執行；`POST /workflows/{id}/retry` 則在同一次執行上從失敗點續跑，已經成功的上游不重跑。
- **Cron 週期性排程**：排程直接指向一條 workflow 定義並帶著自己的輸入，改了定義下次觸發就用新版；由 Celery Beat 定期檢查、到點自動建立並派送，時區與應用程式設定一致。
- **Redis 滑動窗口限流**：每個登入使用者獨立計算請求速率，防止單一來源打爆系統。
- **即時任務狀態推播**：透過 WebSocket 與 Redis Pub/Sub 實現任務狀態即時推播，前端無需輪詢。
- **帳號登入認證**：註冊／登入以 bcrypt 雜湊密碼、JWT 簽發 session token，前端自助註冊帳號即可使用。
- **即時 Ops 儀表板**：React 前端提供任務佇列深度、吞吐量、錯誤率的即時可視化；workflow 詳情頁用同一套畫布以唯讀模式呈現執行進度，節點依狀態上色、WebSocket 即時更新。

---



## 內建支援的任務類型 (Supported Task Handlers)

這份清單由 `app/tasks/catalog.py` 定義、透過 `GET /tasks/types` 提供欄位規格，前端的任務建立表單與 workflow 屬性面板都照它動態產生——**新增一種任務類型不用改前端**。

| 任務類型 (task_type) | 說明 |
| :--- | :--- |
| `input` | workflow 的資料入口。執行時會被換成 Run 表單填入的值（定義沒宣告 `input_schema` 時則用 payload 裡寫死的 JSON），它的結果就是整條 workflow 的「原料」 |
| `fetch_page` | 抓一個網頁並依 CSS selector 抽出欄位，另一種「原料來源」。填了 Item selector 會回傳一個 list，可以直接接 `for_each` 逐項處理；沿用 `http_request` 的 SSRF 檢查，且轉址每一跳都重驗 |
| `python` | 在受限的 subprocess 裡執行一段 Python 程式碼。定義一個 `main()`，它的回傳值會自動成為結果的 `result.value`；上游結果放在全域變數 `inputs` 裡（也可寫成 `main(inputs)`） |
| `shell` | 在受限的 subprocess 裡執行一段 shell 指令。上游結果放在工作目錄的 `inputs.json`，取單一值用 `$(./get_input input_1.price)` |
| `http_request` | 發送一個 HTTP 請求，會擋掉指向內網或 cloud metadata endpoint 的目標 |
| `condition` | 評估一個條件並回傳 `passed=true/false`，本身永遠成功；下游用 `branch_of` + `branch_when` 指向它來實現 if/else 分支 |
| `agent_step` | 執行一個 [Codoctopus](https://github.com/ccoliu/Codoctopus) Agent step——payload 帶 `role`（system prompt）、`instruction`、選填的 `model`（`"provider:model"`）與 `tools`（`read_file` / `write_file` / `list_files` / `http_request` / `run_tests`）。需要 worker 環境裝好 `codoctopus`，見下方安裝說明。 |
> 需要 worker 能 import `codoctopus` 才能使用 `agent_step`。本機開發時 `pip install -e "<codoctopus-checkout>[anthropic]"`（`[anthropic]` 不能省，SDK 是 optional dependency；也可以用 `[openai]` / `[gemini]` / `[all]`，或指到 `ollama:` 模型完全不裝任何 SDK）。
>
> 容器化部署則不用把 codoctopus 裝進每個 worker——`agent_step` 是唯一需要它的 task_type，所以獨立路由到專屬的 `agent_step` queue，只有 `docker compose --profile agent up` 啟動的 `worker-agent` 服務（見 `Dockerfile.agent`）裝了 codoctopus，其餘 worker 完全不受影響。要用這個服務：在 `.env` 設定 `CODOCTOPUS_PATH`（指向本機 Codoctopus checkout 的路徑）與 `AGENT_STEP_DEFAULT_MODEL`，以及該 provider 需要的環境變數（例如 `ANTHROPIC_API_KEY`，或指向本地 OpenAI 相容 server 的 `OPENAI_BASE_URL`）。`agent_step` 若被排到沒有 worker-agent 在跑的環境，會一直卡在 pending，不會失敗也不會誤被其他 worker 執行。

> `python` 與 `shell` 以受限的 subprocess 執行（timeout、CPU / 記憶體上限、清空環境變數，見 `app/tasks/sandbox.py`）。**這不是完整沙箱**——它仍與 worker 共用檔案系統與網路，不要拿來跑不受信任的輸入。

早期的示範 handler（`echo`、`heavy_computation`、`flaky_task`、`job_search` 等）仍註冊在 `TASK_REGISTRY` 裡（既有資料與測試還在引用），但刻意不列進上面的目錄，前端的任務類型選單不會出現它們。

---

## 視覺化 Workflow 編輯器

![Workflow builder](<workflow-builder.png>)

`/workflows/new` 是一張以 React Flow 建成的畫布，自動排版用 dagre；既有定義用 `/definitions/{id}/edit` 開同一張畫布編輯（載入時自動排版），存檔是整份取代，版本號自動 +1：

- **拖拉建置**：左側面板把任務類型拖進畫布就是一個節點，節點之間拉一條線就是 `depends_on`
- **分支即連線**：`condition` 節點右側有 `true` / `false` 兩個出口，從哪個出口拉線出去，就自動設好該步驟的 `branch_of` / `branch_when`，不需要手動對應 step key
- **展開與收斂**：屬性面板的 For each / Reduce from 設定 fan-out 與 fan-in，畫布以虛線標出資料從哪裡來；reduce 步驟會拒絕手動拉入的連線（它的依賴由系統在展開後決定）
- **屬性面板**：右側表單依 `GET /tasks/types` 的欄位規格動態產生；`python` / `shell` 的程式碼欄位是 CodeMirror 編輯器（語法高亮、自動縮排、可放大成 modal 編輯，也可以直接上傳 `.py`）
- **輸入欄位編輯器**：畫布上方可以定義這條 workflow 的 `input_schema`（key／顯示名稱／型別／預設值／必填／選項），執行與排程的表單都照它產生，形狀與 `GET /tasks/types` 的欄位規格相同
- **即時驗證**：前端鏡射了一份後端 `validate_dag` 的規則（見 `frontend/src/features/workflows/validateGraph.ts`），問題會即時標在節點上、列在畫布上方，有錯就擋住送出。後端那份仍是最終把關，兩邊必須同步維護。另有不擋送出的黃色警告，例如 `python` 程式碼裡仍在使用 `{{steps...}}` 模板
- **快捷鍵**：`Delete` 刪除選取的節點或連線、`Esc` 取消選取、`Ctrl+D` 複製節點、`L` 自動排版、`F` 置中

Workflow 詳情頁用**同一套畫布**以唯讀模式呈現實際執行狀況：節點依 task 狀態上色、透過 WebSocket 即時更新，沒被選中的那一邊分支會淡化顯示為 `cancelled`，點任一節點可查看它的 payload 與錯誤訊息。

![Workflow run view](<workflow-run.png>)

上圖是一條巢狀分支的 workflow：`condition_1` 走 `false` 進到 `python_2`，`condition_2` 走 `true` 進到 `shell_2`；沒被選中的 `shell_1`、`shell_3` 連同下游標記為 `cancelled`，整條 workflow 仍是 `Success`——分支沒命中是預期結果，不是失敗。

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

第一次進去先在登入頁註冊一組帳號，然後看側邊欄的 **Getting started**（http://localhost:5173/getting-started ）——那裡有一個從建立到執行的完整例子，也是最快上手的方式。

### 3. 執行測試
```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```
在主機上執行（不是在容器裡）。大部分測試不需要任何外部服務；`tests/test_executor_workflow.py` 是 executor 的整合測試，會連 `.env` 的 `DATABASE_URL` 那台 Postgres，另建一個 `<POSTGRES_DB>_test` 資料庫，把 workflow 的派送、`inputs` 組裝、for_each / reduce（包含展開成 0 項）、分支取消、失敗與續跑整條走過一遍。Celery 派送被換成記錄器，不需要 worker 和 Redis。連不上資料庫時這組測試會 skip，加 `-rs` 可以看到原因；要改連別台就設 `TEST_DATABASE_URL`。

> 主機上如果另外裝了原生 Postgres 並佔用 5432，`localhost:5432` 會連到那一台，錯誤訊息是 `password authentication failed`。這時把 `.env` 的 `POSTGRES_PORT` 和 `DATABASE_URL` 都改成別的 port（例如 5433），再執行 `docker compose up -d postgres`。

### 4. 啟動 Locust 壓力測試
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
| `GET` | `/tasks/{task_id}/logs` | 這個任務的完整執行歷程（由舊到新）：每次重試一筆，含錯誤訊息、結果與執行耗時 |
| `DELETE` | `/tasks/{task_id}` | 刪除指定任務 |

### Workflow Definitions（產線）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/definitions/` | 建立一條 workflow 定義（`steps` + 選填的 `input_schema`），本身不執行 |
| `GET` | `/definitions/` | 分頁列出所有定義，附帶執行次數與最近一次執行 |
| `GET` | `/definitions/{definition_id}` | 查詢單一定義 |
| `PUT` | `/definitions/{definition_id}` | 整份取代；`steps` 或 `input_schema` 有變動時版本號自動 +1 |
| `DELETE` | `/definitions/{definition_id}` | 刪除定義（它的排程一併刪除，已跑過的 run 保留） |
| `POST` | `/definitions/{definition_id}/runs` | 帶一批 `input` 執行一次，回傳這次的 run |
| `GET` | `/definitions/{definition_id}/runs` | 分頁列出這條定義的執行紀錄 |

### Workflow Runs（每一次執行）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `GET` | `/workflows/` | 分頁列出所有 run |
| `GET` | `/workflows/{workflow_id}` | 查詢整體狀態、每個節點對應任務的即時狀態、這次的 `input` 與最終 `result` |
| `POST` | `/workflows/{workflow_id}/rerun` | 用同一份快照與同一份輸入再跑一次，建立一個**新的** run，舊那次完整保留 |
| `POST` | `/workflows/{workflow_id}/retry` | 在**同一筆** run 上從失敗點續跑：失敗的步驟與被它連帶取消的下游重設為 pending，已成功的上游不重跑 |
| `POST` | `/workflows/{workflow_id}/promote-to-schedule` | 把這次 run 所屬的定義與輸入註冊成 cron 週期排程 |
| `DELETE` | `/workflows/{workflow_id}` | 刪除這次 run |
| `POST` | `/workflows/` | **舊路徑**：直接建立一次性的 run（不屬於任何定義），保留給既有腳本與壓測使用 |

一個「餵一批資料進去，下游取用它」的最小範例：
```json
POST /definitions/
{
  "name": "demo-pipeline",
  "input_schema": [
    { "key": "keyword", "label": "關鍵字", "kind": "string", "required": true }
  ],
  "steps": [
    {
      "key": "input_1", "name": "input", "task_type": "input",
      "payload": { "data": "{}" },
      "depends_on": []
    },
    {
      "key": "greet", "name": "build-greeting", "task_type": "python",
      "payload": { "code": "def main():\n    return {'greeting': 'hello ' + inputs['input_1']['keyword']}" },
      "depends_on": ["input_1"]
    }
  ]
}
```
```json
POST /definitions/{definition_id}/runs
{ "input": { "keyword": "backend" } }
```

**資料怎麼流動**

- `python` 步驟：全域變數 `inputs` 是 `{step_key: 上游結果}`，涵蓋**所有祖先步驟**（不只直接上游），型別完整保留；上游是 `python` 時取的是它 `main()` 的回傳值。也可以宣告成 `def main(inputs):`
- `shell` 步驟：同一份資料寫在工作目錄的 `inputs.json`，取單一值用 `$(./get_input input_1.keyword)`（點號路徑對應 python 的中括號）
- `{{steps.<key>.result}}` / `{{steps.<key>.result.<欄位>}}`：其餘任務類型（`http_request`、`condition` 等）用的字串模板，在派送前由 executor 代換。**step key 只能用英數字與底線**，代換的 regex 是 `[a-zA-Z0-9_]+`。這是字串插值，會失去型別，值來自使用者輸入時請優先用上面兩種
- `{{item}}` / `{{item.<欄位>}}`：`for_each` 動態展開時取用當前項目
- `{{items}}`：`reduce_of` 步驟取用被收斂的所有結果。`python` 的 reduce 步驟則直接用 `inputs["<for_each 步驟的 key>"]`，拿到的是**依項目順序排好**的結果 list（不管各項目實際完成的先後），可以跟 for_each 的來源 list 直接 `zip`

**展開與收斂（for_each / reduce）**

- 某個步驟設了 `for_each: <key>`，就會依那個步驟的結果（必須是 list；python 步驟取它 `main()` 的回傳值）逐項展開成 N 個 task，並行執行
- 另一個步驟設 `reduce_of: <for_each 步驟的 key>`，會等所有展開出來的 task 都完成才執行，把它們的結果收成一個 list——這就是 fan-out / fan-in
- reduce 步驟的依賴在展開後由系統自動決定，不能自己設 `depends_on`；也不能同時是 for_each 或分支步驟
- 畫布上兩者都在右側屬性面板設定（For each / Reduce from），以標著 `for each`、`reduce` 的虛線呈現，跟一般依賴的實線區隔
- payload 用模板參照了某個 step，就必須把它加進 `depends_on`，否則建立時會被擋下——不然無法保證它先執行

**分支與失敗**

- `depends_on` 可以填多個 key，支援分支與合併（真正的 DAG，不只是線性鏈）
- `branch_of` + `branch_when` 指向一個 `condition` 步驟，只有結果相符的那一邊會執行；另一邊連同它的下游會被標記為 `cancelled`——這是**預期結果，不代表 workflow 失敗**
- 任一節點徹底失敗（重試耗盡）時，所有下游節點會被自動標記為 `cancelled`，整個 workflow 標記為 `failed`。修掉問題之後可以用 `/retry` 只重跑失敗那一段——沒走到的分支會維持 `cancelled`，不會被誤喚醒

**輸出**：workflow 全部完成時，所有終端節點（沒有其他步驟依賴它）的成功結果會收進 `workflows.result`，格式是 `{step_key: result}`，可在 `GET /workflows/{id}` 的回應與詳情頁的 Result 卡片看到。

### Schedules（週期性排程）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/schedules/` | 建立一個綁定 cron 表達式的排程：指向一條定義（`definition_id`）並帶著每次要用的 `input` |
| `GET` | `/schedules/` | 列出所有排程 |
| `GET` | `/schedules/{schedule_id}` | 查詢單一排程 |
| `PATCH` | `/schedules/{schedule_id}` | 更新名稱、cron、輸入或啟用狀態 |
| `DELETE` | `/schedules/{schedule_id}` | 刪除排程 |

Celery Beat 每分鐘檢查一次所有 `enabled=true` 的排程，`next_run_at` 到期就依**定義當下的內容**建立一份新的 run 並派送根節點，再依 cron 表達式計算下一次執行時間。因為排程存的是 `definition_id` 而不是 steps 的複本，修改定義之後下一次觸發就會用新版。cron 以應用程式設定的時區（`Asia/Taipei`）解讀，跟 `next_run_at` 的顯示、比較邏輯保持一致。

排程的 `input` 在存檔當下就依 `input_schema` 驗證，觸發時再驗一次；若定義改動後輸入不再合法，該次觸發會被跳過並記錄原因，時間照常往前推，不會卡住其他排程。

### 其他
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `GET` | `/health` | API 伺服器健康檢查 |
| `WS` | `/ws/tasks` | WebSocket 即時任務狀態推播 (Redis Pub/Sub) |

`/tasks`、`/definitions`、`/workflows`、`/schedules` 底下所有端點都需要先透過 `/auth/register` 或 `/auth/login` 取得 JWT，帶在 `Authorization: Bearer <token>` header 裡才能存取，並依登入身份受 Redis 滑動窗口限流保護。

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
- **Getting started 頁**：站內的上手教學，用一個實際例子（輸入 → python 判斷 → 條件分支 → 兩條分支的 shell）走完建立、執行、看結果、設排程的流程，並整理了資料傳遞方式與常見問題排查。
- **Tasks 頁**：任務列表、篩選、建立單一任務，狀態透過 WebSocket 即時更新。
- **Workflows 頁**：上半部是所有 workflow 定義（執行次數、最近一次執行狀態，可直接 Run / Edit），下半部是最近的執行紀錄。「New workflow」進入視覺化畫布編輯器（見上方[章節](#視覺化-workflow-編輯器)）。
- **定義詳情頁**：依 `input_schema` 產生的 Run 表單、步驟總覽，以及這條定義的執行紀錄。
- **執行詳情頁**：用同一套畫布以唯讀模式呈現實際執行狀況，每個節點即時顯示狀態，跑完後出現這次的 Input 與 Result，並可 Re-run、從失敗點 Retry 或升級成排程。點任一節點會開啟側邊抽屜，顯示它的 payload 與完整執行歷程（含每一次重試的錯誤訊息，不受重新整理影響）。
- **Schedules 頁**：管理週期性排程——選一條 workflow 定義、填 cron 表達式（含常用預設如「每天 9:00」）與這個排程要用的輸入，顯示下一次/上一次執行時間，可隨時啟用/停用或編輯。
- **Ops 頁**：佇列深度、吞吐量走勢圖、錯誤率等即時監控指標。
