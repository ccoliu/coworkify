"""
{{connections.<name>}}：在步驟的 payload 裡引用使用者自己的密鑰。

- 只允許出現在「發網路請求」的欄位（CONNECTION_FIELDS）。python / shell 不在其中：sandbox 的
  保證是使用者程式碼拿不到任何機密，這個保證不為 connection 破例。
- 資料庫裡的 task.payload 永遠只有佔位字串；worker 在執行前才解密、代換出一份給 handler 用。
- handler 的結果與錯誤訊息存進 task_logs、推上 WebSocket 之前，用 scrub() 把密鑰換回
  <connection:name>——例如 webhook 網址本身就是密鑰，requests 的錯誤訊息常常整個印出網址。
"""
import copy
import json
import re
from typing import Any

from sqlalchemy import select

from app.core.connection_crypto import decrypt
from app.models.connection import Connection

CONNECTION_REF = re.compile(r"\{\{\s*connections\.([a-zA-Z0-9_]+)\s*\}\}")

# task_type -> 可以放 {{connections.x}} 的 payload 欄位（headers 是 dict，看它的值）
CONNECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "http_request": ("url", "headers"),
    "fetch_page": ("url",),
    "notify": ("webhook_url",),
}


def _refs(value: Any) -> set[str]:
    return set(CONNECTION_REF.findall(json.dumps(value, ensure_ascii=False)))


def misplaced_connection_refs(task_type: str, payload: dict) -> list[str]:
    """回傳放錯地方的欄位名稱（空 list = 沒問題）。建立定義時就檢查，執行時再檢查一次。"""
    allowed = CONNECTION_FIELDS.get(task_type, ())
    return sorted(k for k, v in (payload or {}).items() if k not in allowed and _refs(v))


def _placement_error(task_type: str, fields: list[str]) -> str:
    allowed = CONNECTION_FIELDS.get(task_type)
    where = (
        f"only in {', '.join(allowed)}" if allowed
        else f"in {', '.join(f'{t}.{f}' for t, fs in CONNECTION_FIELDS.items() for f in fs)} — not in {task_type} steps"
    )
    return f"{{{{connections.*}}}} can be used {where}; found it in: {', '.join(fields)}"


def resolve_connections(db, task) -> tuple[dict, dict[str, str]]:
    """
    回傳 (給 handler 的 payload, {name: 明文})。沒有引用任何 connection 時原樣回傳 payload。
    用的是 task 擁有者自己的 connection；別人的跟不存在一樣。
    """
    payload = task.payload or {}
    names = _refs(payload)
    if not names:
        return payload, {}

    misplaced = misplaced_connection_refs(task.task_type, payload)
    if misplaced:
        raise ValueError(_placement_error(task.task_type, misplaced))

    rows = db.scalars(
        select(Connection).where(Connection.created_by == task.created_by, Connection.name.in_(names))
    ).all()
    found = {c.name: c for c in rows}
    missing = sorted(names - found.keys())
    if missing:
        raise ValueError(f"Connection not found: {', '.join(missing)} — create it on the Connections page")
    secrets = {name: decrypt(found[name].encrypted_value) for name in names}

    def render(value):
        if isinstance(value, str):
            return CONNECTION_REF.sub(lambda m: secrets[m.group(1)], value)
        if isinstance(value, dict):
            return {k: render(v) for k, v in value.items()}
        if isinstance(value, list):
            return [render(v) for v in value]
        return value

    resolved = copy.deepcopy(payload)
    for field in CONNECTION_FIELDS[task.task_type]:
        if field in resolved:
            resolved[field] = render(resolved[field])
    return resolved, secrets


def scrub(value: Any, secrets: dict[str, str]) -> Any:
    """把結果或錯誤訊息裡出現的密鑰換成 <connection:name>。"""
    if not secrets:
        return value
    if isinstance(value, str):
        # 長的先換，免得一個密鑰剛好是另一個的子字串時只換掉一半
        for name, secret in sorted(secrets.items(), key=lambda kv: -len(kv[1])):
            value = value.replace(secret, f"<connection:{name}>")
        return value
    if isinstance(value, dict):
        return {k: scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secrets) for v in value]
    return value
