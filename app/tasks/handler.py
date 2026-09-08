import asyncio
import os
import tempfile
import time
from pathlib import Path
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

# 7. 執行一個 Codoctopus Plan step：Planner/Agent 決定「做什麼」，
#    Coworkify 的 DAG 排程決定「什麼時候做」，這個 handler 是兩邊真正接起來的地方。
def _agent_step_tool_factories():
    """延遲 import codoctopus 的內建工具，讓沒用到 agent_step 時不需要裝 codoctopus。"""
    from codoctopus.tools.filesystem import ListFilesTool, ReadFileTool, WriteFileTool
    from codoctopus.tools.http import HttpRequestTool
    from codoctopus.tools.testing import RunTestsTool

    return {
        "read_file": ReadFileTool,
        "write_file": WriteFileTool,
        "list_files": ListFilesTool,
        "http_request": HttpRequestTool,
        "run_tests": RunTestsTool,
    }


def _resolve_agent_step_workspace(explicit: str | None) -> Path:
    """
    每個 agent_step task 都要有一個 workspace 給檔案類工具用。沒有明確指定的話，
    退回一個共用的暫存目錄——同一個 workflow 的多個 step 若想共用檔案，
    呼叫端（例如 CoworkifyExecutor）應該明確傳入同一個 workspace 路徑。
    """
    workspace = Path(explicit) if explicit else (
        Path(os.getenv("AGENT_STEP_WORKSPACE_ROOT", tempfile.gettempdir())) / "codoctopus-agent-steps"
    )
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def handle_agent_step(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload:
      role (str, 必填): agent 的 system prompt
      instruction (str, 必填): 這個 step 要做的事
      model (str, 選填): "provider:model"，例如 "anthropic:claude-opus-5"；
        不給的話讀環境變數 AGENT_STEP_DEFAULT_MODEL
      tools (list[str], 選填): 從 read_file / write_file / list_files /
        http_request / run_tests 裡選
      workspace (str, 選填): 檔案類工具的操作目錄
    """
    role = payload.get("role")
    instruction = payload.get("instruction")
    if not role or not instruction:
        raise ValueError("payload.role and payload.instruction are required for agent_step task")

    try:
        from codoctopus.agents import Agent
        from codoctopus.llm import get_provider
        from codoctopus.tools import ToolRegistry
    except ImportError as exc:
        raise RuntimeError(
            "The 'agent_step' task type requires the 'codoctopus' package to be installed "
            "in this worker's environment. Install it with: pip install -e <path-to-codoctopus>"
        ) from exc

    model_ref = payload.get("model") or os.getenv("AGENT_STEP_DEFAULT_MODEL", "anthropic:claude-opus-5")
    provider = get_provider(model_ref)

    tool_names = payload.get("tools") or []
    tools = None
    if tool_names:
        factories = _agent_step_tool_factories()
        unknown = [name for name in tool_names if name not in factories]
        if unknown:
            raise ValueError(f"Unknown tool(s) for agent_step: {unknown}. Available: {sorted(factories)}")
        workspace = _resolve_agent_step_workspace(payload.get("workspace"))
        tools = ToolRegistry([factories[name]() for name in tool_names], workspace=workspace)

    agent = Agent(provider, system=role, tools=tools)
    result = asyncio.run(agent.run(instruction))

    return {"output": result.text}


# 任務路由表：將 task_type 字串映射到對應的 Python 函數
TASK_REGISTRY = {
    "echo": handle_echo,
    "heavy_computation": handle_heavy_computation,
    "flaky_task": handle_flaky_task,
    "http_request": handle_http_request,
    "job_search": handle_job_search,
    "tailor_cv": handle_tailor_cv,
    "job_apply": handle_job_apply,
    "agent_step": handle_agent_step,
}

# 任務路由表：將 task_type 字串映射到對應的 Python 函數
def get_task_handler(task_type: str):
    return TASK_REGISTRY.get(task_type)