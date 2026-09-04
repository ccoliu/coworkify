from email import message
import time
from typing import Dict, Any
from datetime import datetime

import ipaddress
import socket
from urllib.parse import urlparse
import requests

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

def _validate_public_url(url: str) -> None:
    """避免 http_request 任務被拿來打內網 / cloud metadata endpoint (SSRF)"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must start with http:// or https://")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("url is missing a hostname")
    
    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Failed to resolve hostname: {hostname}") from exc
    
    for info in resolved:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"Hostname resolved to a forbidden IP address: {ip}")

def handle_http_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = payload.get("url")
    if not url:
        raise ValueError("payload.url is required for http_request task")

    _validate_public_url(url)

    method = payload.get("method", "GET").upper()
    body = payload.get("body")
    headers = payload.get("headers", {})
    timeout = payload.get("timeout_seconds", 10)

    response = requests.request(
        method, url, headers=headers, json=body, timeout=timeout, allow_redirects=False,
    )

    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text[:2000]

    return {"status_code": response.status_code, "response_body": response_body}

# 4. 模擬搜尋職缺，回傳一份 list（示範 for_each 動態展開用）
def handle_job_search(payload: Dict[str, Any]) -> list:
    keyword = payload.get("keyword", "backend engineer")
    count = payload.get("count", 3)
    return [
        {
            "job_id": f"job-{i + 1}",
            "title": f"{keyword.title()} #{i + 1}",
            "company": f"Demo Company {i + 1}",
            "jd": f"We are looking for a {keyword} with {i + 1}+ years of experience.",
        }
        for i in range(count)
    ]

# 5. 模擬依 JD 客製化履歷（示範用，之後可換成真的 LLM 呼叫）
def handle_tailor_cv(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_title = payload.get("title", "the role")
    jd = payload.get("jd", "")
    return {"tailored_summary": f"Tailored CV for {job_title} based on JD: {jd[:80]}"}

# 6. 模擬投遞履歷（示範用）
def handle_job_apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"applied": True, "job_id": payload.get("job_id")}

# 任務路由表：將 task_type 字串映射到對應的 Python 函數
TASK_REGISTRY = {
    "echo": handle_echo,
    "heavy_computation": handle_heavy_computation,
    "flaky_task": handle_flaky_task,
    "http_request": handle_http_request,
    "job_search": handle_job_search,
    "tailor_cv": handle_tailor_cv,
    "job_apply": handle_job_apply,
}

# 任務路由表：將 task_type 字串映射到對應的 Python 函數
def get_task_handler(task_type: str):
    return TASK_REGISTRY.get(task_type)