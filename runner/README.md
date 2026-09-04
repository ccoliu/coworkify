# Coworkify Local Runner

讓 Coworkify 的某些任務跑在你自己的機器上，而不是共用的 Celery worker 上——
適合需要控制本機瀏覽器、存取本機檔案，或執行你不想上傳到伺服器的自訂程式碼的情境。

## 安裝

```bash
pip install requests
```

## 1. 建立 runner

在前端「Runners」頁面按「New runner」，或直接呼叫 API：

```bash
curl -X POST http://localhost:8000/runners/ \
  -H "Authorization: Bearer <你的 JWT>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-laptop"}'
```

回應會包含一個 `token`，**只會顯示這一次**，請馬上複製起來。

## 2. 寫自己的任務邏輯

複製 `handlers.example.py` 成 `handlers.py`，把 `TASK_REGISTRY` 換成你自己的 task_type 對應函式。

## 3. 啟動 agent

```bash
python agent.py --api http://localhost:8000 --token <上一步拿到的 token> --handlers handlers.py
```

它會每隔幾秒問一次伺服器「有沒有指派給我的任務」，認領到就在這台機器上執行，完成後把結果回報回去。

## 4. 建立任務時指定這個 runner

建立 task 或 workflow step 時，把 `runner_id` 設成這個 runner 的 id（`GET /runners/` 可以查到），
`task_type` 用你在 `handlers.py` 裡註冊的名字。這個 task 就不會進 Celery 佇列，
而是等這支 agent 認領執行。
