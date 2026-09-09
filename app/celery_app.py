import os
from celery import Celery
from dotenv import load_dotenv
from kombu import Queue
from pathlib import Path

# 載入 env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

#: task_type 字串 -> 專屬 queue 名稱。目前只有 agent_step 需要 codoctopus 這種比較
#: 重的依賴（LLM SDK），所以獨立一條 queue，讓只有裝了 codoctopus 的 worker 去消費，
#: 其他 task_type 一律留在預設 queue，不用改動任何現有的 worker。
DEDICATED_QUEUES = {
    "agent_step": "agent_step",
}
DEFAULT_QUEUE = "celery"

# init
celery_app = Celery(
    "coworkify",
    broker=REDIS_URL, # 任務佇列，傳遞任務
    backend=REDIS_URL, # 任務結果，儲存
    include=["app.tasks.executor", "app.tasks.scheduler"] # 告訴 Celery 要自動載入的任務模組
)

# advanced

celery_app.conf.update(
    task_serializer="json",  # 序列化任務
    accept_content=["json"], # 接受 JSON 格式
    result_serializer="json", # 回傳 JSON
    timezone="Asia/Taipei", # 使用台灣時區
    enable_utc=True, # 啟用 UTC
    task_track_started = True, # 追蹤任務開始狀態
    worker_prefetch_multiplier=1, # 一次只抓取一個任務
    broker_transport_options={
        "priority_steps": list(range(10)),
        "sep": ":", # 區分優先級與任務名稱
        "queue_order_strategy": "priority"
    },
    # 明確宣告每條 queue，讓 broker 端就算 dedicated queue 的 worker 還沒啟動也不會出錯。
    task_default_queue=DEFAULT_QUEUE,
    task_queues=[Queue(DEFAULT_QUEUE)] + [Queue(name) for name in set(DEDICATED_QUEUES.values())],
)

celery_app.conf.beat_schedule = {
    "check-due-workflow-schedules": {
        "task": "coworkify.check_due_schedules",
        "schedule": 60.0 # 每60秒檢查一次排程
    }
}