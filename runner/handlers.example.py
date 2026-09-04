"""
複製這個檔案成 handlers.py，把 TASK_REGISTRY 換成你自己要在本機執行的任務邏輯。

執行方式：
    python agent.py --api http://localhost:8000 --token <你的 runner token> --handlers handlers.py

建立 workflow / task 的時候，把該 step 的 runner_id 設成這個 runner 的 id，
task_type 設成這裡註冊的名字（例如 "local_job_apply"），
它就不會進共用的 Celery 佇列，而是等這支 agent 認領執行。
"""

from typing import Any, Dict


def handle_local_job_apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    範例：在本機用瀏覽器自動化工具（例如 Playwright/Selenium）幫指定職缺投遞履歷。
    這裡先用假邏輯示範，換成你自己的實作即可。
    """
    job_id = payload.get("job_id")
    print(f"(example) applying locally for {job_id}...")
    return {"applied_locally": True, "job_id": job_id}


def handle_local_file_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """範例：讀寫本機檔案系統（不適合放在共用 worker 上做的事）"""
    path = payload.get("path")
    return {"path": path, "note": "換成你自己的本機檔案處理邏輯"}


TASK_REGISTRY = {
    "local_job_apply": handle_local_job_apply,
    "local_file_task": handle_local_file_task,
}
