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
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

from app.tasks.sandbox import DEFAULT_TIMEOUT_SECONDS, python_command, run_sandboxed, INPUTS_FILENAME, SCRIPT_FILENAME, shell_command

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

_FETCH_MAX_BYTES = 2 * 1024 * 1024
_FETCH_MAX_REDIRECTS = 3
_FETCH_TEXT_LIMIT = 4000
_FETCH_USER_AGENT = "Coworkify/0.1 (+https://github.com/ccoliu/coworkify)"

def _fetch_html(url: str, timeout) -> tuple[str, str]:
    """
    抓一個 HTML 頁面，回傳 (最終網址, HTML)。
    
    刻意自己處理轉址：requests 的 allow_redirects 會直接跟著跳，導致
    「第一跳是公開網址、第二跳指回內網」可以繞過 SSRF 檢查。這裡每一跳都重驗一次。
    """
    current = url
    for _ in range(_FETCH_MAX_REDIRECTS + 1):
        _validate_public_url(current)
        response = requests.get(
            current,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": _FETCH_USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError(f"Got {response.status_code} without a Location header")
            current = urljoin(current, location)
            continue


        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if not any(t in content_type for t in ("html", "xml", "text/plain")):
            raise ValueError(
                f"Not an HTML page (Content-Type: {content_type or 'unknown'})——"
                f"要打 API 請改用 http_request 任務類型"
            )

        chunks = []
        total = 0
        for chunk in response.iter_content(8192):
            total += len(chunk)
            if total > _FETCH_MAX_BYTES:
                raise ValueError(f"Page is larger than {_FETCH_MAX_BYTES // 1024 // 1024}MB")
            chunks.append(chunk)
        
        html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
        return current, html

    raise ValueError(f"Too many redirects (>{_FETCH_MAX_REDIRECTS})")

def _parse_json_payload_field(raw, field_name: str) -> dict:
    """前端的 code 欄位給的是 JSON 字串；透過 API 直接送 dict 也接受。"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"payload.{field_name} 不是合法的 JSON: {exc}") from exc
    
    if not isinstance(parsed, dict):
        raise ValueError(f"payload.{field_name} 解析後不是物件")
    return parsed

def _extract_fields(node, fields: dict, base_url: str) -> dict:
    """
    依 {輸出名稱: selector} 抽值。selector 後面加 '@屬性' 可以取屬性而不是文字，
    例如 'a @href'；href / src 會自動補成絕對網址。找不到的欄位回 None，不丟錯——
    網頁改版時讓下游自己決定要不要容忍，比整條 workflow 失敗好。
    """
    extracted = {}
    for name, spec in fields.items():
        selector, _, attr = str(spec).partition("@")
        selector = selector.strip()
        attr = attr.strip()

        found = node.select_one(selector) if selector else node
        if found is None:
            extracted[name] = None
            continue
        
        if attr:
            value = found.get(attr)
            if value and attr in ("href", "src"):
                value = urljoin(base_url, value)
        else:
            value = found.get_text(" ", strip=True)
        extracted[name] = value
    return extracted

def handle_fetch_page(payload: Dict[str, Any]) -> Any:
    """
    抓一個固定網頁當作 workflow 的原料。

    有 item_selector 時回傳的是「一個 list」而不是包了 metadata 的 dict——
    for_each 的契約就是上游結果必須是 list，這樣抓列表頁可以直接逐項展開。
    """
    url = payload.get("url")
    if not url:
        raise ValueError("payload.url is required for fetch_page task")
    
    timeout = payload.get("timeout_seconds", 10)
    fields = _parse_json_payload_field(payload.get("fields"), "fields")
    item_selector = str(payload.get("item_selector") or "").strip()
    max_items = int(payload.get("max_items") or 20)

    final_url, html = _fetch_html(url, timeout)
    soup = BeautifulSoup(html, "html.parser")

    if item_selector:
        nodes = soup.select(item_selector)[:max_items]
        if fields:
            return [_extract_fields(node, fields, final_url) for node in nodes]
        return [{"text": node.get_text(" ", strip=True)} for node in nodes]

    if fields:
        return _extract_fields(soup, fields, final_url)

    # 沒指定要抽什麼就給一份「整頁純文字」，先看得到內容再回頭寫 selector
    title = soup.title.get_text(strip=True) if soup.title else None
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return {"title": title, "text": soup.get_text(" ", strip=True)[:_FETCH_TEXT_LIMIT]}

_PY_RESULT_MARKER = "__COWORKIFY_RESULT__"

# 附加在使用者程式碼後面的驅動程式碼：如果使用者定義了一個叫 main 的函式，
# 就呼叫它、把回傳值序列化成 JSON 印到一行特殊標記後面。沒有 main 的話這段
# if 判斷式在執行期就是 False，完全不影響原本的程式（含它自己的 print 輸出）。
#
# main 有帶參數時，會把上游步驟的結果（{step_key: result}）讀進來傳給它；
# 沒帶參數的 main() 照舊直接呼叫，所以既有的程式碼不受影響。
# 真正被執行的入口：載入使用者的 script.py，再把 main() 的回傳值序列化成 JSON，
# 印在一行特殊標記後面。沒有 main 的話什麼都不做，使用者自己的 print 輸出不受影響。
#
# 上游步驟的結果（{step_key: result}）有兩種取用方式，兩種都可以：
#   - 直接用全域的 inputs（含 main() 裡面，以及模組層級的程式碼）
#   - 把 main 宣告成帶一個參數，例如 main(inputs)
_PY_RUNNER = f"""
import inspect
import json
import os
import runpy

_dir = os.path.dirname(os.path.abspath(__file__))

try:
    with open(os.path.join(_dir, {INPUTS_FILENAME!r}), encoding="utf-8") as _f:
        inputs = json.load(_f)
except FileNotFoundError:
    # 沒有上游（根節點）或不在 workflow 裡時就是空的
    inputs = {{}}

# init_globals 讓 inputs 成為使用者程式碼裡的全域名稱；run_name 讓
# `if __name__ == "__main__":` 這種寫法照常成立。
_globals = runpy.run_path(
    os.path.join(_dir, {SCRIPT_FILENAME!r}),
    init_globals={{"inputs": inputs}},
    run_name="__main__",
)

_main = _globals.get("main")
if callable(_main):
    try:
        _wants_inputs = len(inspect.signature(_main).parameters) > 0
    except (TypeError, ValueError):
        _wants_inputs = False

    _result = _main(inputs) if _wants_inputs else _main()
    try:
        _serialized = json.dumps(_result)
    except (TypeError, ValueError):
        _serialized = json.dumps(str(_result))
    print({_PY_RESULT_MARKER!r} + _serialized)
"""


def handle_python(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    在受限 subprocess 裡跑一段 python 程式碼，見 app/tasks/sandbox.py 的說明。

    如果程式碼定義了 main()，它的回傳值會被自動抓出來放進結果的 "value" 欄位
    （JSON 序列化過，所以下游可以用 '{{steps.<key>.result.value}}' 拿到真正
    型別的值，不用自己 print() 再從 stdout 字串裡解析）。

    main 可以宣告一個參數，例如 main(inputs)——executor 會把直接上游的結果
    以 {{step_key: result}} 的形式傳進來（見 executor.collect_upstream_inputs）。
    """
    code = payload.get("code")
    if not code:
        raise ValueError("payload.code is required for python task")

    result = run_sandboxed(
        lambda tmpdir: python_command(
            code, tmpdir, runner=_PY_RUNNER, inputs=payload.get("inputs")
        ),
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
        lambda tmpdir: shell_command(command, tmpdir, inputs=payload.get("inputs")),
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

# 8. workflow 的資料入口：把 payload 裡的 JSON 原樣變成這一步的 result，
#    下游就能用 '{{steps.<key>.result.欄位}}' 取用。不需要新的模板語法——
#    它就是一個「結果是常數」的普通 task。
def handle_input(payload: Dict[str, Any]) -> Any:
    raw = payload.get("data", "")
    # 前端的 code 欄位給的是 JSON 字串；透過 API 直接送 dict/list 也接受
    if isinstance(raw, (dict, list)):
        return raw
    if not str(raw).strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"payload.data 不是合法的 JSON: {exc}") from exc


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
    "input": handle_input,
    "fetch_page": handle_fetch_page,
}

# 任務路由表：將 task_type 字串映射到對應的 Python 函數
def get_task_handler(task_type: str):
    return TASK_REGISTRY.get(task_type)