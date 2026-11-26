# Coworkify - Distributed Task Scheduling & Execution Platform

[English](README.en.md) | 繁體中文

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg?style=flat&logo=PostgreSQL&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D.svg?style=flat&logo=Redis&logoColor=white)](https://redis.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=Python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat&logo=React&logoColor=white)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat&logo=Docker&logoColor=white)](https://www.docker.com/)

**Coworkify** 是一個輕量、高效且具備彈性的分散式任務排程與管理平台（架構靈感源自 Apache Airflow 與 Celery）。使用者與微服務可以透過 RESTful API 定義、排程、追蹤與監控各類非同步任務，並支援多任務串接成 DAG workflow，使用Redis + Postgres + Celery 組成，以 Locust 壓測，單一 API process 約 240 RPS，開 4 個 process 時 300 個併發使用者下 554 RPS、零錯誤（見[壓力測試報告](#壓力測試報告-benchmark-results)）。

![alt text](<coworkify.png>)
---

## 核心特色 (Key Features)

- **完整的任務生命週期管理**：支援 `pending` ➔ `running` ➔ `success` / `failed` / `retrying` / `waiting` / `cancelled` 狀態機流轉。
- **高性能非同步架構**：以 FastAPI 作為核心 API 閘道，結合 Redis 實現低延遲訊息佇列 (Message Broker)。
- **任務優先級調度 (Priority Queue)**：每個任務帶 0–9 的優先度，**數字越小越先被 worker 取走**（0 最優先、9 最後，這是 Celery 搭配 Redis broker 的規則），讓重要任務插隊。
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
- **事件觸發**：除了 cron，產線也可以由外部事件啟動。webhook 觸發器接受 Bearer secret 或 GitHub 的 HMAC 簽章，用 JSON 路徑把 body 對應成 run 的輸入、用 filter 只接想要的事件，重送的同一個 delivery 不會建出第二個 run；workflow 觸發器則在另一條產線成功、失敗或任一結束時啟動下游，建立時就擋掉會繞回自己的循環。
- **Sub-workflow**：把另一條定義當成一個步驟來跑，等它結束、把它的 `result` 交給下游。等待期間跟 `wait_for` 一樣不佔 worker；子 run 失敗時，錯誤訊息會指出是哪個子 run 的哪一步。
- **Redis 滑動窗口限流**：每個登入使用者獨立計算請求速率，防止單一來源打爆系統。
- **即時任務狀態推播**：透過 WebSocket 與 Redis Pub/Sub 實現任務狀態即時推播，前端無需輪詢。
- **帳號登入認證**：註冊／登入以 bcrypt 雜湊密碼、JWT 簽發 session token，前端自助註冊帳號即可使用。
- **資源隔離**：定義、run、task、排程都屬於建立它的使用者——系統代替使用者建立的也一樣（run 裡的 task、for_each 展開的 task、排程觸發的 run）。別人的資源一律回 404（不回 403，免得透露那個 id 存在）；`/ws/tasks` 也只推送自己的 task。
- **密鑰管理（Connections）**：GitHub token、Discord webhook 這類密鑰以 Fernet 加密存放，寫進去之後 API 不會再回傳。步驟用 `{{connections.<name>}}` 引用，worker 執行當下才解密代換——資料庫裡的 payload 只有佔位字串，結果與錯誤訊息存進 log 前會把密鑰換回 `<connection:name>`。只能用在發網路請求的欄位，`python` / `shell` 拿不到。
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
| `agent_step` | 執行一個 [Codoctopus](https://github.com/ccoliu/Codoctopus) Agent step——payload 帶 `role`（system prompt）、`instruction`、選填的 `model`（`"provider:model"`）與 `tools`（`read_file` / `write_file` / `list_files` / `http_request` / `run_tests`）。填了 `output_fields`（例如 `{"fixable": "boolean", "effort": ["small", "large"]}`）會改用 structured output，結果直接是那個物件，下游可以 `inputs["judge"]["fixable"]` 取值。需要 worker 環境裝好 `codoctopus`，見下方安裝說明。 |
| `wait_for` | sensor：反覆用 GET 檢查一個回傳 JSON 的網址，直到某個欄位（`path`，例如 `workflow_runs.0.status`）等於 `expected`，或超過 `timeout_seconds`。適合等 CI、部署這類外部工作，見下方說明 |
| `notify` | 送一則 Discord webhook 通知（標題、內文、連結、等級決定顏色），通常放在 workflow 最後一步。webhook URL 預設讀 worker 的 `DISCORD_WEBHOOK_URL` 環境變數——它等同密碼，不建議寫進 workflow 定義 |
| `subworkflow` | 執行另一條 workflow 定義、等它跑完，結果是那個子 run 的 `result`。不在 `GET /tasks/types` 的目錄裡——它的欄位取決於被呼叫的定義，建構器從左側的 Workflows 區塊加入，見下方說明 |
> 需要 worker 能 import `codoctopus` 才能使用 `agent_step`。本機開發時 `pip install -e "<codoctopus-checkout>[anthropic]"`（`[anthropic]` 不能省，SDK 是 optional dependency；也可以用 `[openai]` / `[gemini]` / `[all]`，或指到 `ollama:` 模型完全不裝任何 SDK）。CI 測的是釘住的 Codoctopus 版本（`.github/workflows/ci.yml` 的 `CODOCTOPUS_REF`），本機要跟它一致就在 checkout 裡 `git checkout <那個 SHA>`；另有每週排程改測 Codoctopus 的 `main`，提早發現上游的破壞性改動。
>
> 容器化部署則不用把 codoctopus 裝進每個 worker——`agent_step` 是唯一需要它的 task_type，所以獨立路由到專屬的 `agent_step` queue，只有 `docker compose --profile agent up` 啟動的 `worker-agent` 服務（見 `Dockerfile.agent`）裝了 codoctopus，其餘 worker 完全不受影響。要用這個服務：在 `.env` 設定 `CODOCTOPUS_PATH`（指向本機 Codoctopus checkout 的路徑）與 `AGENT_STEP_DEFAULT_MODEL`，以及該 provider 需要的環境變數（例如 `ANTHROPIC_API_KEY`，或指向本地 OpenAI 相容 server 的 `OPENAI_BASE_URL`）。`agent_step` 若被排到沒有 worker-agent 在跑的環境，會一直卡在 pending，不會失敗也不會誤被其他 worker 執行。

> `python` 與 `shell` 以受限的 subprocess 執行（timeout、CPU / 記憶體上限、清空環境變數，見 `app/tasks/sandbox.py`）。**這不是完整沙箱**——它仍與 worker 共用檔案系統與網路，不要拿來跑不受信任的輸入。

### `wait_for`：等外部條件成立

`python` / `shell` 最多跑 60 秒，等不了要跑十分鐘的 CI。`wait_for` 用 reschedule 模式：條件還沒成立時 task 轉成 `waiting`、排定下一次檢查，立刻把 worker 讓出來。等一小時，實際佔用 worker 的只有每次檢查的那一下。

| 欄位 | 說明 | 預設 / 範圍 |
| :--- | :--- | :--- |
| `url` | 要檢查的網址，SSRF 檢查與 `http_request` 相同，不跟隨轉址 | 必填 |
| `headers` | JSON 物件，可以放 `{{connections.<name>}}` | 選填 |
| `path` | 回應 JSON 裡要看的欄位，點分隔，數字代表陣列索引。找不到視為還沒好 | 必填 |
| `expected` | 欄位等於它就算完成，比對會分型別；可以是單一值或 list（任一相符即可）。畫布上填文字就是比對字串，要比對數字、布林或多個值請填 JSON 陣列，例如 `[200]` | 必填 |
| `interval_seconds` | 檢查間隔 | 30，5–600 |
| `timeout_seconds` | 從第一次檢查算起最多等多久 | 3600，1–86400 |

完成後的結果是 `{"status_code", "response_body", "waited_seconds"}`，下游可以直接讀 `response_body` 裡的欄位。

- **`waiting` 不是失敗**：不消耗 `retry_count`，`task_logs` 也不會每次檢查都寫一筆，只有進入 `waiting`、成功、失敗時才寫。
- **逾時直接失敗，不重試**：重試只是再等一次。下游會被串連取消，`POST /workflows/{id}/retry` 續跑時 sensor 從頭計時。
- **檢查本身出錯算一般失敗**：回應非 2xx 或不是 JSON 會走既有的重試與指數退避，逾時的計時不會因此歸零。
- **延遲訊息遺失會自動補回**：countdown 的訊息放在 worker 記憶體裡，worker 重啟就沒了。Beat 每分鐘找過了排定時間 5 分鐘還沒被檢查的 task，重新派送；`waiting` 的 task 要到期才認領得到，所以多出來的訊息不會變成第二條輪詢鏈。
- **已知限制**：`waiting` 跟 `running` 一樣不會被平行分支的失敗取消，這條 workflow 已經標成 `failed` 時，sensor 仍會繼續檢查到成立或逾時。

> 既有資料庫要先套 `scripts/migrations/2026_11_08_task_wait_started_at.sql`（`create_all` 不會替既有的表加欄位），再更新 api / worker / beat：
>
> ```powershell
> # PowerShell：一定要指定 UTF-8，否則中文註解會把 SQL 吃掉
> Get-Content -Encoding UTF8 scripts/migrations/2026_11_08_task_wait_started_at.sql | docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
> ```
>
> ```bash
> # bash
> docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -' < scripts/migrations/2026_11_08_task_wait_started_at.sql
> ```

### `subworkflow`：把另一條 workflow 當成步驟

一條產線做到一半，需要另一條已經寫好的產線（例如「抓 issue 並判斷」）時，不用把它的步驟複製過來，加一個 `subworkflow` 步驟呼叫它就好。payload 是要呼叫的定義，加上那條定義 `input_schema` 裡的欄位：

```json
{ "key": "triage", "name": "triage", "task_type": "subworkflow",
  "payload": { "definition_id": "<被呼叫的定義 id>", "repo": "apache/airflow", "hours": 1 },
  "depends_on": ["input_1"] }
```

步驟成功時的結果就是子 run 的 `workflows.result`（`{終端步驟 key: 結果}`），下游用 `inputs["triage"]["digest"]` 取值。

- **等待不佔 worker**：第一次執行時建立子 run（`trigger_kind = "subworkflow"`），步驟轉成 `waiting`。子 run 一結束就把這個步驟叫醒，不用等下一次檢查；叫醒的訊息遺失時，有每 60 秒一次的備援檢查與 Beat 的回收機制接手。
- **失敗會說清楚**：子 run 失敗時，步驟以 `Child run <id> (<名稱>) failed at step '<步驟>'` 失敗，下游照常被串連取消。
- **預設不重試**：`subworkflow` 步驟的 `max_retries` 預設是 0，因為重試會建立一個新的子 run、整條重跑。用 `/retry` 續跑時也一樣是新的子 run，舊的那次保留著可以查。
- **修不好的錯誤直接失敗**：被呼叫的定義已經刪除、輸入不合它的 `input_schema`、巢狀超過 5 層，這幾種重試也不會好，跳過重試直接失敗。
- **存檔時就檢查**：被呼叫的定義必須存在而且是自己的、傳入的每個欄位都要在它的 `input_schema` 裡宣告過，而且不能直接或間接呼叫回自己。
- **畫布上互相連結**：步驟節點有「Open child run ↗」連到子 run；子 run 的畫布左側多一個「Called by」節點指回父 run 與那個步驟，詳情頁上方也有麵包屑。

![Sub-workflow step](<subworkflow-run.png>)

早期的示範 handler（`echo`、`heavy_computation`、`flaky_task`、`job_search` 等）仍註冊在 `TASK_REGISTRY` 裡（既有資料與測試還在引用），但刻意不列進上面的目錄，前端的任務類型選單不會出現它們。

---

## 視覺化 Workflow 編輯器

![Workflow builder](<workflow-builder.png>)

`/workflows/new` 是一張以 React Flow 建成的畫布，自動排版用 dagre；既有定義用 `/definitions/{id}/edit` 開同一張畫布編輯（載入時自動排版），存檔是整份取代，版本號自動 +1：

- **拖拉建置**：左側面板把任務類型拖進畫布就是一個節點，節點之間拉一條線就是 `depends_on`
- **分支即連線**：`condition` 節點右側有 `true` / `false` 兩個出口，從哪個出口拉線出去，就自動設好該步驟的 `branch_of` / `branch_when`，不需要手動對應 step key
- **展開與收斂**：屬性面板的 For each / Reduce from 設定 fan-out 與 fan-in，畫布以虛線標出資料從哪裡來；reduce 步驟會拒絕手動拉入的連線（它的依賴由系統在展開後決定）
- **屬性面板**：右側表單依 `GET /tasks/types` 的欄位規格動態產生；`python` / `shell` 的程式碼欄位是 CodeMirror 編輯器（語法高亮、自動縮排、可放大成 modal 編輯，也可以直接上傳 `.py`）
- **呼叫其他 workflow**：左側面板的 Workflows 區塊列出可以呼叫的定義，拖進畫布就是一個 `subworkflow` 步驟，屬性面板依被呼叫定義的 `input_schema` 產生輸入欄位。區塊一開始只載入標了 ★ 的常用定義，其他的按「Show other workflows」才去抓，定義很多時打開建構器也不會一次拉下全部；★ 在 Workflows 列表、定義詳細頁和這個區塊都能切換
- **輸入欄位編輯器**：畫布上方可以定義這條 workflow 的 `input_schema`（key／顯示名稱／型別／預設值／必填／選項），執行與排程的表單都照它產生，形狀與 `GET /tasks/types` 的欄位規格相同
- **即時驗證**：前端鏡射了一份後端 `validate_dag` 的規則（見 `frontend/src/features/workflows/validateGraph.ts`），問題會即時標在節點上、列在畫布上方，有錯就擋住送出。後端那份仍是最終把關，兩邊必須同步維護。另有不擋送出的黃色警告，例如 `python` 程式碼裡仍在使用 `{{steps...}}` 模板
- **快捷鍵**：`Delete` 刪除選取的節點或連線、`Esc` 取消選取、`Ctrl+D` 複製節點、`L` 自動排版、`F` 置中

Workflow 詳情頁用**同一套畫布**以唯讀模式呈現實際執行狀況：節點依 task 狀態上色、透過 WebSocket 即時更新，沒被選中的那一邊分支會淡化顯示為 `cancelled`，點任一節點可查看它的 payload 與錯誤訊息。由觸發器或 sub-workflow 串起來的 run 會以虛線節點畫在兩側：左邊是啟動這次 run 的上游 run 或父 run，右邊是這次 run 結束後觸發的下游 run，點一下就跳過去。

![Workflow run view](<workflow-run.png>)

上圖是一條巢狀分支的 workflow：`condition_1` 走 `false` 進到 `python_2`，`condition_2` 走 `true` 進到 `shell_2`；沒被選中的 `shell_1`、`shell_3` 連同下游標記為 `cancelled`，整條 workflow 仍是 `Success`——分支沒命中是預期結果，不是失敗。

---

## 實戰案例：GitHub issue 分流流水線

一條每小時自動執行的流水線：抓 [apache/airflow](https://github.com/apache/airflow) 過去一小時新開的 issue，讓本機的 LLM 逐條判斷「好不好修」，分級後推到 Discord。熱門專案的新 issue 很快就會被人認領，這條流水線的用途是在別人之前先看到值得接的那幾條。

![Issue triage pipeline](<pipeline-canvas.png>)

| 步驟 | 類型 | 做什麼 |
| :--- | :--- | :--- |
| `input_1` | `input` | 這次執行的參數：`repo`、`hours`（時間窗長度）、`max_issues` |
| `window` | `python` | 算出對齊整點的時間窗，組出 GitHub Search API 的查詢網址 |
| `fetch` | `http_request` | 呼叫 Search API |
| `shape` | `python` | 整理成 issue list，並先用程式判斷「是否已經有人在處理」：作者在 issue 表單勾了願意送 PR，或 Timeline API 查得到會關閉它的 PR |
| `judge` | `agent_step` | `for_each: shape`，每條 issue 並行一個 LLM 判斷，structured output 回傳固定欄位 |
| `digest` | `python` | `reduce_of: judge`，把 issue 與判斷結果依序配對，分成 🟢 / 🟡 / ⚪ 三級並組成訊息 |
| `condition_3` | `condition` | `digest` 的 `has_news` 為真才往下走 |
| `notify` | `notify` | 送出 Discord 通知 |

幾個設計決定：

- **模型只回答事實，分級由程式決定。** `judge` 的 `output_fields` 只問內文寫了什麼：是不是功能提案、有沒有重現步驟、有沒有指出具體原因、修改範圍多大。「可以直接動手」還是「要先查原因」是 `digest` 裡幾行 `if` 決定的。9B 的本機模型直接回答「好不好修」時判斷飄忽，回答「內文有沒有 stack trace」就穩定得多；分級規則要調整時也只要改程式，不必重寫 prompt 再重新驗證模型的行為。
- **已經有人認領的 issue 不交給模型判斷。** 作者勾選願意送 PR、或已經有會關閉它的 PR，一律歸到 ⚪，優先於模型的結果——這些是查得到的事實，不需要猜。
- **時間窗對齊整點。** 每次查 `[整點 - hours, 整點)`，查詢上界減一秒，避開 GitHub 範圍查詢兩端都包含的行為。就算排程晚了幾分鐘觸發，相鄰兩次的時間窗仍然首尾相接，不重複也不遺漏。
- **沒有新 issue 也照常收斂。** `shape` 回傳空 list 時 `judge` 展開成 0 項，`digest` 仍會執行並回傳 `has_news: false`，由 `condition_3` 擋下通知——實際上大部分時段都走這條路。
- **資料傳遞不經字串模板。** `digest` 直接 `zip(inputs["shape"], inputs["judge"])`；reduce 拿到的結果依項目順序排好，跟各 issue 實際判斷完成的先後無關。

![Discord notification](<pipeline-discord.png>)

模型是透過 LM Studio 在本機執行的 `qwen/qwen3.5-9b`，走 OpenAI 相容 API（`AGENT_STEP_DEFAULT_MODEL=openai:qwen/qwen3.5-9b`、`OPENAI_BASE_URL` 指向 LM Studio），由 `worker-agent` 執行。排程 cron 是 `5 * * * *`，也就是每小時第 5 分鐘。從 2026-09-22 開始持續運行到 2026-09-24，共執行 55 次：49 次沒有新 issue、6 次送出通知，總共判斷了 17 條 issue。另有 2 次失敗，原因是 LM Studio 把模型卸載了，`judge` 重試耗盡，流水線本身沒有問題；這種情況修好之後可以用 `/retry` 從失敗點續跑。

---

## 快速開始 (Quick Start)

### 配置需求
- Docker / Docker Compose

### 1. 設定環境變數
複製一份 `.env`（範例參考 `docker-compose.yml` 所需的變數：`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`JWT_SECRET` 等），改成自己的值。`JWT_SECRET` 用來簽發登入 token，建議用 `python -c "import secrets; print(secrets.token_hex(32))"` 產生一組隨機字串。

`.env` 另外需要 `CONNECTIONS_KEY`（加密 connection 的金鑰），用 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 產生。可以用逗號放多把：加密用第一把、解密每一把都試，換金鑰時把新的放前面、舊的留著，直到每個 connection 都重新存過。

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
在主機上執行（不是在容器裡）。大部分測試會連 `.env` 的 `DATABASE_URL` 那台 Postgres，另建一個 `<POSTGRES_DB>_test` 資料庫，每個測試結束後清空；Celery 派送被換成記錄器、限流器的 Redis 換成假的，所以不需要 worker 和 Redis。連不上資料庫時這些測試會 skip，加 `-rs` 可以看到原因；要改連別台就設 `TEST_DATABASE_URL`。

- `test_executor_*.py`：workflow 的派送、`inputs` 組裝、for_each / reduce（包含展開成 0 項）、分支取消、失敗與續跑、task 認領與回收卡在 RUNNING 的 task
- `test_api_*.py`：用 FastAPI `TestClient` 打真正的 app——註冊登入與 JWT、限流、task 的建立／查詢／軟刪除、定義的版本號、run 的輸入驗證（422）、rerun 與 retry、排程的 CRUD 與 promote-to-schedule
- `test_scheduler.py`：cron 排程的觸發、失敗記錄、台北時區
- `test_wait_for.py`：sensor 的比對與夾值、`waiting` 不消耗重試、逾時直接失敗、重複訊息不會變成第二條輪詢鏈、遺失的延遲訊息會被補回
- `test_webhook_triggers.py` / `test_workflow_triggers.py`：webhook 的 Bearer 與 HMAC 驗證、filter、輸入對應、delivery id 去重、GitHub ping、body 大小與限流；workflow 觸發器的結束狀態比對、循環檢查、觸發鏈深度上限、同一個結果只觸發一次、retry 後成功會觸發 success
- `test_subworkflows.py`：子 run 的建立與喚醒、成功時交出 `result`、失敗訊息、retry 建新的子 run、不重試的錯誤、巢狀深度上限、存檔時的循環與輸入檢查、worker 在建好子 run 後掛掉不會多建一個
- `test_definition_favorites.py`：標 ★ 不改版本號也不改排序、列表的 `favorite` 篩選、別人的定義回 404
- `test_handlers.py`：SSRF 防護（內網、cloud metadata、IPv4-mapped、轉址的每一跳）、`http_request`、`fetch_page` 的欄位擷取與大小上限、`notify`、`condition`、`input`。網路與 DNS 全部替換，不會真的連線
- `test_sandbox.py`：真的起 subprocess 跑 `python` / `shell` 步驟——回傳值與 `inputs`、`get_input`、不繼承 worker 的機密環境變數、逾時連同背景子程序一起殺掉、記憶體上限。只在 Linux 上執行（Windows 會 skip）
- `e2e/`：不替換任何東西，對一套正在跑的 API + Celery worker + Redis 從外部打 HTTP / WebSocket——分支加 for_each / reduce 的 workflow 跑到完成、併發下的 join 只執行一次、`self.retry` 的退避重試、WebSocket 推播。只在設了 `E2E_BASE_URL` 時執行（例如 `E2E_BASE_URL=http://localhost:8000 pytest tests/e2e -q`），CI 在獨立的 `e2e` job 裡起真的服務來跑

CI 以 `--cov-fail-under` 設了覆蓋率下限。`app/` 底下每個目錄都有 `__init__.py`，沒被任何測試 import 的檔案才會以 0% 算進總數，數字不會偏高。

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
| `GET` | `/definitions/` | 分頁列出所有定義，附帶執行次數與最近一次執行；`?favorite=true` 只列標了 ★ 的、`false` 只列其他的 |
| `GET` | `/definitions/{definition_id}` | 查詢單一定義 |
| `PUT` | `/definitions/{definition_id}` | 整份取代；`steps` 或 `input_schema` 有變動時版本號自動 +1 |
| `DELETE` | `/definitions/{definition_id}` | 刪除定義（它的排程一併刪除，已跑過的 run 保留） |
| `PUT` / `DELETE` | `/definitions/{definition_id}/favorite` | 標成常用／取消。重複呼叫沒有副作用，也不會改版本號或 `updated_at` |
| `POST` | `/definitions/{definition_id}/runs` | 帶一批 `input` 執行一次，回傳這次的 run |
| `GET` | `/definitions/{definition_id}/runs` | 分頁列出這條定義的執行紀錄 |

### Workflow Runs（每一次執行）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `GET` | `/workflows/` | 分頁列出所有 run |
| `GET` | `/workflows/{workflow_id}` | 查詢整體狀態、每個節點對應任務的即時狀態、這次的 `input` 與最終 `result`；由什麼啟動（`trigger_kind`），以及串在一起的 `upstream_run`、`downstream_runs`、`parent_run` / `parent_step_name`，`subworkflow` 步驟另有 `child_workflow_id` |
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

### Connections（密鑰）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/connections/` | 建立一組密鑰（`name` + `value`），值加密存放；回應不含值 |
| `GET` | `/connections/` | 列出自己的 connection（名稱、說明、更新時間，沒有值） |
| `PATCH` | `/connections/{connection_id}` | 換一個新的值或改說明；名稱不能改，步驟靠它引用 |
| `DELETE` | `/connections/{connection_id}` | 刪除；引用它的步驟之後執行會失敗並說明原因 |

可以引用的位置：`http_request` 的 `url` 與 `headers`、`wait_for` 的 `url` 與 `headers`、`fetch_page` 的 `url`、`notify` 的 `webhook_url`，例如 `{"Authorization": "Bearer {{connections.github}}"}`。放在其他欄位（包括 `python` / `shell` 的程式碼）的引用，在建立定義時就會被擋下（422）。

### Schedules（週期性排程）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/schedules/` | 建立一個綁定 cron 表達式的排程：指向一條定義（`definition_id`）並帶著每次要用的 `input` |
| `GET` | `/schedules/` | 列出所有排程 |
| `GET` | `/schedules/{schedule_id}` | 查詢單一排程 |
| `PATCH` | `/schedules/{schedule_id}` | 更新名稱、cron、輸入或啟用狀態 |
| `DELETE` | `/schedules/{schedule_id}` | 刪除排程 |

Celery Beat 每分鐘檢查一次所有 `enabled=true` 的排程，`next_run_at` 到期就依**定義當下的內容**建立一份新的 run 並派送根節點，再依 cron 表達式計算下一次執行時間。因為排程存的是 `definition_id` 而不是 steps 的複本，修改定義之後下一次觸發就會用新版。cron 以應用程式設定的時區（`Asia/Taipei`）解讀，跟 `next_run_at` 的顯示、比較邏輯保持一致。

排程的 `input` 在存檔當下就依 `input_schema` 驗證，觸發時再驗一次；若定義改動後輸入不再合法，該次觸發會被跳過，原因記在排程的 `last_error` / `last_error_at`（Schedules 頁面以紅字顯示），`last_run_at` 不變——它只代表「真的建立了 run」；時間照常往前推，不會卡住其他排程，下一次觸發成功就清掉錯誤。

### Triggers（事件觸發）
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `POST` | `/triggers/` | 建立觸發器。`kind: "webhook"` 的回應會帶 `secret` 與 `hook_path`，**secret 只會顯示這一次**；`kind: "workflow"` 要給 `source_definition_id` 與 `on_status`（`success` / `failed` / `any`） |
| `GET` | `/triggers/` | 列出自己的觸發器，含 `last_triggered_at`、`last_error` |
| `GET` | `/triggers/{trigger_id}` | 查詢單一觸發器 |
| `PATCH` | `/triggers/{trigger_id}` | 更新名稱、輸入對應、filter、`on_status` 或啟用狀態 |
| `POST` | `/triggers/{trigger_id}/rotate-secret` | 換一組 webhook secret，舊的立刻失效 |
| `DELETE` | `/triggers/{trigger_id}` | 刪除觸發器，已經建立的 run 保留 |
| `POST` | `/hooks/{trigger_id}` | **webhook 接收端，不用 JWT**，靠觸發器自己的 secret 驗證 |

兩種觸發器共用同一套設定：`input_mapping` 是 `{輸入欄位: JSON 路徑}`，從事件內容取出這次 run 的輸入，事件的其他部分不會帶進 run；`filter` 是 `{JSON 路徑: 期望值}`，每個條件都成立才建 run，期望值是 list 代表其中之一，比對分型別（跟 `wait_for` 相同）。`input_mapping` 用了定義沒宣告的欄位，存檔時就會被擋下。前端在側邊欄的 **Triggers** 頁管理。

![Triggers page](<triggers.png>)

**Webhook**

```json
POST /triggers/
{ "name": "on-push", "kind": "webhook", "definition_id": "<定義 id>",
  "input_mapping": { "commit": "head_commit.id", "branch": "ref" },
  "filter": { "ref": "refs/heads/main" } }
```
```bash
curl -X POST http://localhost:8000/hooks/<trigger_id> \
  -H "Authorization: Bearer <secret>" -H "Content-Type: application/json" \
  -d '{"ref": "refs/heads/main", "head_commit": {"id": "abc123"}}'
```

- **兩種驗證擇一**：自己的腳本用 `Authorization: Bearer <secret>`；GitHub 不能自訂 header，改用 secret 對 body 簽 HMAC-SHA256，放在 `X-Hub-Signature-256`。GitHub 那邊的設定是 Payload URL 填 `https://<對外網址>/hooks/<trigger_id>`、Content type 選 `application/json`、Secret 填建立時拿到的 secret（本機開發要另外用 tunnel 才收得到）。兩種都用 `compare_digest` 比對。
- **回應碼**：建立 run 回 `202 {"workflow_id"}`；filter 不符合回 `204`；secret 或簽章錯誤回 `401`；輸入不合 `input_schema` 回 `422`，原因同時記在觸發器的 `last_error`，Triggers 頁會顯示。驗證失敗**不會**寫 `last_error`，因為任何人都打得到這個網址。
- **重送不會重複建 run**：帶了 `X-GitHub-Delivery` 或 `Idempotency-Key` 時，同一個值第二次進來回 `200 {"workflow_id", "duplicate": true}`。兩次同時到達也只會建一個，由資料庫的 unique constraint 擋下後到的那次。
- **GitHub 的 ping**：建立 webhook 時 GitHub 會先送一個 ping，直接回 `200 pong`，不會被當成事件拿去對應輸入。
- **限制**：body 最大 1 MB，必須是 JSON 物件；每個觸發器每分鐘最多 60 次。限流以觸發器為單位，不看來源 IP，因為 GitHub 是從一大池 IP 送出的。

**上一條產線結束後**

workflow 觸發器在來源產線的 run 以 `on_status` 指定的結果結束時，啟動目標產線。`input_mapping` 和 `filter` 讀的是 `{"workflow_id", "status", "result", "input"}`，例如用 `"items": "result.digest.items"` 把上游的成品接成下游的輸入，或用 `{"result.digest.has_news": true}` 只在有東西時才往下走。

- **只接自己的 run**：觸發器的擁有者必須也是上游 run 的擁有者。
- **每個結果只觸發一次**：同一個上游 run、同一種結束狀態只會啟動一次下游。上游失敗後用 `/retry` 修好而成功，會再觸發 `success` 那一邊；retry 之後又失敗，不會再觸發一次 `failed`。
- **不會繞成循環**：建立時沿著既有的 workflow 觸發器檢查目標會不會走回來源，停用的觸發器也算（之後重新啟用時不會再檢查）。兩個請求同時建出互相指向的觸發器時，循環檢查可能各自都通過，所以另有第二道保險：觸發鏈最多 10 層。
- **下游出錯不影響上游**：下游的輸入不合法或建立失敗，只記在觸發器的 `last_error`，已經結束的上游 run 狀態不變。

> 既有資料庫要先依序套用 `scripts/migrations/` 裡的 `2026_11_22_workflow_triggers.sql`、`2026_11_23_workflow_completion_triggers.sql`、`2026_11_24_definition_favorites.sql`（指令同上面 `wait_for` 那段，換掉檔名即可），再重啟 api / worker / beat。

### 其他
| Method | Endpoint | 說明 |
| :--- | :--- | :--- |
| `GET` | `/health` | API 伺服器健康檢查 |
| `WS` | `/ws/tasks` | WebSocket 即時任務狀態推播 (Redis Pub/Sub) |

`/tasks`、`/definitions`、`/workflows`、`/schedules`、`/triggers` 底下所有端點都需要先透過 `/auth/register` 或 `/auth/login` 取得 JWT，帶在 `Authorization: Bearer <token>` header 裡才能存取，並依登入身份受 Redis 滑動窗口限流保護。每個使用者只看得到、改得了自己的資源。`/ws/tasks` 因為瀏覽器的 WebSocket 不能自訂 header，JWT 放在 query string：`/ws/tasks?token=<JWT>`。`/hooks/{trigger_id}` 是唯一不用 JWT 的端點，見上方 Triggers 一節。

---

## 壓力測試報告 (Benchmark Results)

2026-10-27 量測，每一輪都在**全新的空資料庫**上跑，條件相同：

- **環境**：Docker Desktop（Windows，VM 分到 8 CPU / 6 GB），Locust 在主機上跑；API 是單一 uvicorn process（同正式設定，只是沒開 `--reload`），Celery worker `concurrency=4`，Postgres 15、Redis 7
- **負載**：每個虛擬使用者先註冊取得 JWT，接著循環：`GET /tasks`（權重 3）、`POST /tasks`（2）、`POST /workflows` 建立 3 節點 workflow（1）、`GET /health`（1），每次間隔 0.1–0.5 秒；每秒增加 20 個使用者，跑 2 分鐘

| 併發使用者 | 吞吐量 | 平均延遲 | p50 | p95 | p99 | 失敗 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 50 | 147.5 RPS | 34 ms | 17 ms | 76 ms | 120 ms | 0 |
| 100 | **242.5 RPS** | 104 ms | 96 ms | 220 ms | 300 ms | 0 |
| 150 | 240.0 RPS | 307 ms | 320 ms | 500 ms | 640 ms | 0 |

100 人時各端點的數字：

| API 端點 | 內容 | 吞吐量 | 平均延遲 | p95 |
| :--- | :--- | :--- | :--- | :--- |
| `GET /tasks` | 依擁有者過濾的分頁查詢 | 103.3 RPS | 103 ms | 200 ms |
| `POST /tasks` | 寫入 task + 派送進佇列 | 68.3 RPS | 125 ms | 230 ms |
| `POST /workflows` | 建立 3 節點 workflow + 派送根節點 | 35.0 RPS | 139 ms | 250 ms |
| `GET /health` | 不碰資料庫 | 35.1 RPS | 20 ms | 42 ms |

**解讀**

- **單一 API process 大約 240 RPS 就到頂。** 從 100 人加到 150 人，吞吐量沒有增加、延遲變成 3 倍——多出來的請求都在排隊。壓測當下 API 容器的 CPU 是 120%，Postgres 只有 30–40%，瓶頸在 API process 本身（同步的 SQLAlchemy 呼叫跑在 thread pool 裡，受 GIL 限制），不在資料庫。要再往上，下一步是多開 uvicorn worker process 或改用 async 的資料庫層。
- **API 收得下的量 ≠ worker 做得完的量。** 2 分鐘內 API 收下約 8,000 個 task 和 4,000 個 workflow，`concurrency=4` 的 worker 同期間只做完約 1,000 個——測試流量裡三分之一是會 `sleep(1)` 的 `heavy_computation`。上表量的是 API 的收件能力；佇列裡的積壓是在壓測結束後才慢慢消化掉的。

**這次壓測抓到的 bug：資料庫連線預算。** 第一輪在 150 人時出現 24 個 500，Postgres 的 log 是 `FATAL: sorry, too many clients already`：每個 process（API、每個 worker 子 process、beat）的連線池上限都是 100，加起來遠超過 Postgres 預設的 100 條。把所有 process 都改小（10 + 10）反而讓 API 死結——一個請求會先在 thread 裡跑 `get_current_user` 拿走一條連線，再排隊等 thread 跑 endpoint；連線池比 thread pool（40 條）小時，兩邊互等到 `pool_timeout` 才變成 500，150 人時吞吐量掉到 5 RPS。最後的設定是 API 50 條（不小於 thread pool）、worker 與 beat 每個 process 5 條，全部加起來 85 條，小於 100；上表就是這個設定下的結果，壓測期間最多用到 60 條連線。

### 多個 API process

上面的瓶頸在單一 API process，所以接著用 `uvicorn --workers N` 多開 process 再量一次（2026-10-28，改用一台獨立的 Postgres 容器、`max_connections=400`，其餘條件相同）：

| API process | 併發使用者 | 吞吐量 | p95 | 失敗 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 150 | 236 RPS | 460 ms | 0 |
| 1 | 300 | 226 RPS | 1,200 ms | 0 |
| 2 | 300 | 373 RPS | 850 ms | 0 |
| 4 | 300 | **554 RPS** | 450 ms | 0 |

4 個 process 是單一 process 的 2.4 倍；這時 Postgres 的 CPU 已經到 110%，下一個瓶頸換成資料庫。單一 process 在 300 人時吞吐量持平、延遲變長，多出來的請求在排隊，沒有任何失敗。

**多 process 壓測抓到的三個 bug**——第一次跑時，多 process 的那幾輪全部失敗，單一 process 在 300 人時整個卡死：

1. **多個 process 同時啟動就整個停掉。** 每個 process 啟動時都會跑 `create_all`；在空資料庫上，兩個 process 同時查到「表不存在」、同時建表，後到的撞上 duplicate key，uvicorn 看到有 child 啟動失敗就停掉整個服務。修法：建表前先拿 Postgres advisory lock，讓它們排隊。
2. **驗證完身分後，連線一直被占著。** `get_current_user` 在 thread 裡查使用者，請求接著排隊等另一條 thread 跑 endpoint——這段等待期間連線沒有還回去，排隊中、什麼都沒做的請求就把連線池占滿，等滿 30 秒變成 500。修法：查完使用者就結束交易、把連線還回連線池。
3. **同時處理的請求比連線多時互卡。** 一個同步請求會在 thread pool 裡跑好幾段（驗證、endpoint、序列化回應），連線跨過這幾段一直被拿著。卡住當下 40 條 thread 全在等連線，50 條連線全被「在等 thread 的請求」拿著，CPU 0%。uvicorn 的 `--limit-concurrency` 解決不了——它算的是開著的連線，keep-alive 的閒置連線也算，結果大量 503。修法：寫一個 middleware，同時處理的 HTTP 請求最多 40 個（小於連線池的 50），其餘在 event loop 裡排隊，排隊時還沒碰資料庫，所以不可能互卡。

這三個都有對應的測試（`tests/test_startup.py`、`tests/test_auth_connection_release.py`、`tests/test_concurrency_limit.py`）。用多 process 跑的設定在 `docker-compose.prod.yml`：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile agent up -d
```

> 舊版 README 的 194.5 RPS（2026-08-30）是在認證改成 JWT、加上資源隔離與 task 認領機制之前，在另一套條件下量的，已由上表取代。

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
