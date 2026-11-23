"""
Webhook 觸發器用到的純函式：驗證來源、從 body 取出 run 的輸入、判斷 filter。
不碰資料庫和 HTTP，app/api/hooks.py 負責把它們串起來。
"""
import hashlib
import hmac
import secrets
from typing import Any

from app.tasks.handler import _MISSING, _lookup_json_path, _same_json_value

SIGNATURE_PREFIX = "sha256="


def new_secret() -> str:
    # 32 bytes 的隨機值，URL-safe，貼進 GitHub 的 Secret 欄位或 Authorization header 都不用跳脫
    return secrets.token_urlsafe(32)


def is_authorized(secret: str, body: bytes, authorization: str | None, signature: str | None) -> bool:
    """
    兩種方式擇一：
    - Authorization: Bearer <secret>，給自己寫的腳本、curl
    - X-Hub-Signature-256: sha256=<HMAC-SHA256(secret, body)>，給 GitHub——
      GitHub 的 webhook 不能自訂 Authorization header，只會用 secret 簽 body

    一律用 compare_digest 比對，回應時間不會洩漏「猜對了前幾個字」。
    """
    if signature:
        if not signature.startswith(SIGNATURE_PREFIX):
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature[len(SIGNATURE_PREFIX):].encode(), expected.encode())
    if authorization:
        scheme, _, token = authorization.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(token.strip().encode(), secret.encode())
    return False


def matches_filter(body: Any, conditions: dict) -> bool:
    """
    每個條件都要成立。期望值是 list 代表「其中之一」；
    比對跟 wait_for 一樣分型別（True 不等於 1、"200" 不等於 200）。
    路徑不存在算不符合。
    """
    for path, expected in conditions.items():
        actual = _lookup_json_path(body, path)
        if actual is _MISSING:
            return False
        accepted = expected if isinstance(expected, list) else [expected]
        if not any(_same_json_value(actual, value) for value in accepted):
            return False
    return True


def extract_input(body: Any, mapping: dict) -> dict:
    """
    依 mapping 從 body 取出 run 輸入。路徑不存在的欄位不放進去，
    交給 resolve_run_input 補預設值或回報必填。body 的其他部分一律不帶進 run。
    """
    extracted = {}
    for field, path in mapping.items():
        value = _lookup_json_path(body, path)
        if value is not _MISSING:
            extracted[field] = value
    return extracted
