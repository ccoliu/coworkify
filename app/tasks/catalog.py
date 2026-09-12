# ---------------------------------------------------
# Coworkify — the task-type catalog the frontend renders its "New task" /
# workflow-step forms from (GET /tasks/types). Every task_type here must
# have a matching handler in app/tasks/handler.py's TASK_REGISTRY.
#
# The original demo handlers (echo, heavy_computation, flaky_task,
# job_search, tailor_cv, job_apply) stay registered in TASK_REGISTRY —
# existing rows and tests still reference them by name — but are
# deliberately left out of this catalog: this project has moved from toy
# demo tasks to a curated, real-ish task-type set, and this list is what
# the UI's task-type picker actually shows.
# ---------------------------------------------------

from __future__ import annotations

_AGENT_TOOL_OPTIONS = [
    {"value": "read_file", "label": "Read file"},
    {"value": "write_file", "label": "Write file"},
    {"value": "list_files", "label": "List files"},
    {"value": "http_request", "label": "HTTP request"},
    {"value": "run_tests", "label": "Run tests"},
]

_CONDITION_OPERATOR_OPTIONS = [
    {"value": "eq", "label": "= (equals)"},
    {"value": "ne", "label": "≠ (not equals)"},
    {"value": "gt", "label": "> (greater than)"},
    {"value": "gte", "label": "≥ (greater or equal)"},
    {"value": "lt", "label": "< (less than)"},
    {"value": "lte", "label": "≤ (less or equal)"},
    {"value": "contains", "label": "contains"},
    {"value": "not_contains", "label": "does not contain"},
    {"value": "is_true", "label": "is true"},
    {"value": "is_false", "label": "is false"},
    {"value": "is_empty", "label": "is empty"},
    {"value": "is_not_empty", "label": "is not empty"},
]

_HTTP_METHOD_OPTIONS = [{"value": m, "label": m} for m in ("GET", "POST", "PUT", "PATCH", "DELETE")]

_SANDBOX_HELP = (
    "以受限 subprocess 執行（timeout、CPU/記憶體上限、環境變數清空）；"
    "不是完整沙箱，仍與 worker 共用檔案系統和網路，請勿放入機密操作。"
)

TASK_TYPE_CATALOG = [
    {
        "task_type": "python",
        "label": "Python",
        "description": "在受限的 subprocess 裡執行一段 Python 程式碼。定義一個 main()，"
                       "它的回傳值會自動變成結果的 result.value（不用自己 print）。",
        "fields": [
            {
                "key": "code",
                "label": "Code",
                "kind": "code",
                "default": "",
                "language": "python",
                "required": True,
                "help": _SANDBOX_HELP
                + " 若定義了 main()，其回傳值（需可 JSON 序列化，例如 True/False/數字/字串/list/dict）"
                  "會自動出現在下游可用 '{{steps.<key>.result.value}}' 參照的欄位裡。",
                "upload_accept": ".py",
            },
            {"key": "timeout_seconds", "label": "Timeout (seconds)", "kind": "number", "default": 10, "required": False, "help": "上限 60 秒。"},
        ],
    },
    {
        "task_type": "shell",
        "label": "Shell",
        "description": "在受限的 subprocess 裡執行一段 shell 指令。",
        "fields": [
            {"key": "command", "label": "Command", "kind": "code", "default": "", "required": True, "help": _SANDBOX_HELP},
            {"key": "timeout_seconds", "label": "Timeout (seconds)", "kind": "number", "default": 10, "required": False, "help": "上限 60 秒。"},
        ],
    },
    {
        "task_type": "http_request",
        "label": "HTTP Request",
        "description": "發送一個 HTTP 請求（會擋掉內網 / cloud metadata endpoint）。",
        "fields": [
            {"key": "url", "label": "URL", "kind": "string", "default": "https://httpbin.org/get", "required": True},
            {"key": "method", "label": "Method", "kind": "select", "default": "GET", "required": False, "options": _HTTP_METHOD_OPTIONS},
            {"key": "timeout_seconds", "label": "Timeout (seconds)", "kind": "number", "default": 10, "required": False},
        ],
    },
    {
        "task_type": "condition",
        "label": "Condition",
        "description": "評估一個條件，永遠成功並回傳 passed=true/false。下游步驟可以指定"
                       "「branch_of = 這個 step、branch_when = true 或 false」，只在對應的"
                       "結果出現時才執行，實現 if/else 分支。",
        "fields": [
            {
                "key": "left",
                "label": "Left",
                "kind": "string",
                "default": "",
                "required": False,
                "help": "留空就好——只要這個 condition 在 workflow 裡只依賴一個上游 step，"
                        "系統會自動帶入該 step 的結果（上游是有 main() 的 python task 時"
                        "取它的回傳值）。上游有多個、或想比較巢狀欄位時才需要明確填，"
                        "格式是 '{{steps.<key>.result.欄位}}'。",
            },
            {"key": "operator", "label": "Operator", "kind": "select", "default": "eq", "required": True, "options": _CONDITION_OPERATOR_OPTIONS},
            {"key": "right", "label": "Right", "kind": "string", "default": "", "required": False,
             "help": "is_true / is_false / is_empty / is_not_empty 這幾個 operator 不需要填 Right。"},
        ],
    },
    {
        "task_type": "agent_step",
        "label": "Agent (Codoctopus)",
        "description": "執行一個 Codoctopus agent step。需要 worker 環境裝好 codoctopus。",
        "fields": [
            {"key": "role", "label": "Role (system prompt)", "kind": "text", "default": "", "required": True},
            {"key": "instruction", "label": "Instruction", "kind": "text", "default": "", "required": True},
            {
                "key": "model",
                "label": "Model",
                "kind": "string",
                "default": "",
                "required": False,
                "help": "格式 'provider:model'，例如 anthropic:claude-opus-5；留空用預設。",
            },
            {"key": "tools", "label": "Tools", "kind": "multiselect", "default": [], "required": False, "options": _AGENT_TOOL_OPTIONS},
            {
                "key": "workspace",
                "label": "Workspace path",
                "kind": "string",
                "default": "",
                "required": False,
                "help": "留空則用共用暫存目錄；同一個 workflow 的多個 step 要共用檔案時才需要指定。",
            },
        ],
    },
]
