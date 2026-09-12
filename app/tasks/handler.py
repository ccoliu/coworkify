import asyncio
import json
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

from app.tasks.sandbox import DEFAULT_TIMEOUT_SECONDS, python_command, run_sandboxed

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

_PY_RESULT_MARKER = "__COWORKIFY_RESULT__"

# 附加在使用者程式碼後面的驅動程式碼：如果使用者定義了一個叫 main 的函式，
# 就呼叫它、把回傳值序列化成 JSON 印到一行特殊標記後面。沒有 main 的話這段
# if 判斷式在執行期就是 False，完全不影響原本的程式（含它自己的 print 輸出）。
# 這樣使用者不用自己 print(json.dumps(...))，寫一個回傳 True/False（或任何
# JSON 可序列化值）的 main() 就好，結果會出現在 task 結果的 "value" 欄位。
_PY_DRIVER = f"""

if 'main' in dir() and callable(main):
    import json as __coworkify_json
    __coworkify_result = main()
    try:
        __coworkify_serialized = __coworkify_json.dumps(__coworkify_result)
    except (TypeError, ValueError):
        __coworkify_serialized = __coworkify_json.dumps(str(__coworkify_result))
    print({_PY_RESULT_MARKER!r} + __coworkify_serialized)
"""


def handle_python(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    在受限 subprocess 裡跑一段 python 程式碼，見 app/tasks/sandbox.py 的說明。

    如果程式碼定義了 main()，它的回傳值會被自動抓出來放進結果的 "value" 欄位
    （JSON 序列化過，所以下游可以用 '{{steps.<key>.result.value}}' 拿到真正
    型別的值，不用自己 print() 再從 stdout 字串裡解析）。
    """
    code = payload.get("code")
    if not code:
        raise ValueError("payload.code is required for python task")

    result = run_sandboxed(
        lambda tmpdir: python_command(code + _PY_DRIVER, tmpdir),
        shell=False,
        timeout_seconds=payload.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
    )

    value = None
    clean_lines = []
    for line in result["stdout"].splitlines():
        if line.startswith(_PY_RESULT_MARKER):
            try:
                value = json.loads(line[len(_PY_RESULT_MARKER):])
            except ValueError:
                pass
        else:
            clean_lines.append(line)
    result["stdout"] = "\n".join(clean_lines)
    result["value"] = value
    return result


def handle_shell(payload: Dict[str, Any]) -> Dict[str, Any]:
    """在受限 subprocess 裡跑一段 shell 指令，見 app/tasks/sandbox.py 的說明。"""
    command = payload.get("command")
    if not command:
        raise ValueError("payload.command is required for shell task")

    return run_sandboxed(
        command,
        shell=True,
        timeout_seconds=payload.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
    )


_CONDITION_OPERATORS = {
    "eq": lambda l, r: l == r,
    "ne": lambda l, r: l != r,
    "gt": lambda l, r: l > r,
    "gte": lambda l, r: l >= r,
    "lt": lambda l, r: l < r,
    "lte": lambda l, r: l <= r,
    "contains": lambda l, r: r in l,
    "not_contains": lambda l, r: r not in l,
    "is_true": lambda l, r: l is True,
    "is_false": lambda l, r: l is False,
    "is_empty": lambda l, r: not l,
    "is_not_empty": lambda l, r: bool(l),
}


def handle_condition(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    分支節點：依 operator 比較 left/right。這個 task 永遠成功，回傳
    {"passed": bool, ...}——條件不成立不代表「這個 task 失敗」，真正的 if/else 是
    下游步驟用 branch_of/branch_when 指向這個 condition 來實現的：見
    app/tasks/executor.py 的 advance_workflow，選錯邊的分支會被取消，不會讓整條
    workflow 變成 FAILED。

    left 在 workflow 裡通常不用自己填：只要這個 condition 剛好只依賴一個上游 step，
    executor 會在派送前自動帶入該 step 的結果（見 resolve_condition_left）。
    """
    operator = payload.get("operator")
    if operator not in _CONDITION_OPERATORS:
        raise ValueError(
            f"Unknown operator '{operator}' for condition task. "
            f"Available: {sorted(_CONDITION_OPERATORS)}"
        )

    # 沒有 left 就直接報錯，不要拿 None 去比較——那會悄悄得到 passed=False，
    # 讓 workflow 走錯分支而且完全看不出哪裡設錯了。
    if "left" not in payload or payload["left"] == "":
        raise ValueError(
            "payload.left is required for condition task. 在 workflow 裡可以留空由系統"
            "自動帶入上游結果，但前提是這個 condition 剛好只依賴一個上游 step——"
            "目前不是這種情況（沒有上游、或上游超過一個），請明確指定 left，"
            "例如 '{{steps.<key>.result.value}}'。"
        )

    left = payload.get("left")
    right = payload.get("right")
    try:
        passed = _CONDITION_OPERATORS[operator](left, right)
    except TypeError as exc:
        raise ValueError(f"Can't evaluate {left!r} {operator} {right!r}: {exc}") from exc

    return {"passed": bool(passed), "left": left, "operator": operator, "right": right}


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
    "python": handle_python,
    "shell": handle_shell,
    "condition": handle_condition,
}

# 任務路由表：將 task_type 字串映射到對應的 Python 函數
def get_task_handler(task_type: str):
    return TASK_REGISTRY.get(task_type)