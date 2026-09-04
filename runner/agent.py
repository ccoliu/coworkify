"""
Coworkify local runner agent.

在你自己的機器上跑這支程式，它會定期向 Coworkify API 詢問「有沒有指派給我的任務」，
認領到之後在**這台機器上**執行你自己寫的 handler（例如控制瀏覽器、讀寫本機檔案等
不適合、或不該放在共用 worker 上執行的邏輯），完成後把結果回報給伺服器。

用法：
    pip install requests
    python agent.py --api http://<你的 Coworkify 網址>:8000 --token <建立 runner 時拿到的 token>

預設會讀同目錄下的 handlers.py（可用 --handlers 指定其他路徑），
裡面要有一個 TASK_REGISTRY = {task_type: function} 的字典，
可以參考 handlers.example.py。
"""

import argparse
import importlib.util
import sys
import time
from types import ModuleType

import requests

# Windows 的預設主控台編碼常常不是 UTF-8，錯誤訊息裡若混到非 ASCII 字元
# print() 可能會丟 UnicodeEncodeError 或印出亂碼，這裡強制轉成 UTF-8 並容錯。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass  # Python < 3.7，沒有 reconfigure 就算了


def load_handlers(path: str) -> dict:
    spec = importlib.util.spec_from_file_location("local_handlers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load handlers file: {path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = getattr(module, "TASK_REGISTRY", None)
    if not isinstance(registry, dict):
        raise RuntimeError(f"{path} must define a dict named TASK_REGISTRY")
    return registry


def run(api: str, token: str, handlers_path: str, poll_interval: float):
    registry = load_handlers(handlers_path)
    headers = {"X-Runner-Token": token}
    print(f"[coworkify-runner] loaded {len(registry)} task_type(s): {list(registry.keys())}")
    print(f"[coworkify-runner] polling {api} every {poll_interval}s (Ctrl+C to stop)")

    while True:
        try:
            resp = requests.get(f"{api}/runner/tasks/next", headers=headers, timeout=15)
            resp.raise_for_status()
            task = resp.json()
        except Exception as exc:
            print(f"[coworkify-runner] poll failed: {exc}")
            time.sleep(poll_interval)
            continue

        if not task:
            time.sleep(poll_interval)
            continue

        task_id = task["id"]
        task_type = task["task_type"]
        payload = task["payload"]
        print(f"[coworkify-runner] claimed task {task_id} ({task_type}), running...")

        handler = registry.get(task_type)
        try:
            if handler is None:
                raise ValueError(
                    f"no local handler for task_type='{task_type}'; "
                    f"add it to TASK_REGISTRY in {handlers_path}"
                )
            result = handler(payload)
            _report(api, headers, task_id, {"status": "success", "result": result})
            print(f"[coworkify-runner] task {task_id} done")
        except Exception as exc:
            _report(api, headers, task_id, {"status": "failed", "error": str(exc)})
            print(f"[coworkify-runner] task {task_id} failed: {exc}")


def _report(api: str, headers: dict, task_id: str, body: dict):
    resp = requests.post(
        f"{api}/runner/tasks/{task_id}/complete", headers=headers, json=body, timeout=15
    )
    resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description="Coworkify local runner agent")
    parser.add_argument("--api", required=True, help="Coworkify API 位址，例如 http://localhost:8000")
    parser.add_argument("--token", required=True, help="建立 runner 時拿到的 token")
    parser.add_argument("--handlers", default="handlers.py", help="本機 task handler 檔案路徑")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="輪詢間隔秒數")
    args = parser.parse_args()

    run(args.api.rstrip("/"), args.token, args.handlers, args.poll_interval)


if __name__ == "__main__":
    main()
