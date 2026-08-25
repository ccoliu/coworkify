from email import message
import time
from typing import Dict, Any
from datetime import datetime


#define business logics

# 1. 模擬打招呼
def handle_echo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simple echo task"""
    message = payload.get("message", "Hello, Coworkify!")
    return {"message": message, "echoed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

# 2. 模擬耗時運算
def handle_heavy_computation(payload: Dict[str, Any]) -> Dict[str, Any]:
    duration = payload.get("duration_seconds", 3)
    time.sleep(duration)
    return {"computed": True, "slept_seconds": duration}

# 3. 模擬可能失敗的任務 (用來測試自動重試機制)
def handle_flaky_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    should_fail = payload.get("should_fail", True)
    if should_fail:
        raise RuntimeError("模擬任務執行出錯！觸發重試機制！")
    return {"status": "Task finished successfully without errors"}

# 任務路由表：將 task_type 字串映射到對應的 Python 函數
TASK_REGISTRY = {
    "echo": handle_echo,
    "heavy_computation": handle_heavy_computation,
    "flaky_task": handle_flaky_task,
}

# 任務路由表：將 task_type 字串映射到對應的 Python 函數
def get_task_handler(task_type: str):
    return TASK_REGISTRY.get(task_type)