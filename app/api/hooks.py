"""
POST /hooks/{trigger_id}：外部系統（GitHub、自己的腳本）用 webhook 觸發一條產線。

不需要使用者的 JWT，靠每個觸發器自己的 secret 驗證（見 app/core/webhooks.py）。
所以這個 router 不掛 get_current_user，body 大小、限流都在這裡自己處理。

回應：
- 202 {"workflow_id"}：建立了 run
- 200 {"workflow_id", "duplicate": true}：同一個 delivery id 之前已經建過（GitHub 重送）
- 200 {"status": "pong"}：GitHub 建立 webhook 時送的 ping
- 204：filter 不符合，沒有建 run
- 401：secret 或簽章不對
- 404：觸發器不存在、停用，或不是 webhook 觸發器
- 422：取出來的輸入不合定義的 input_schema（也會記在觸發器的 last_error）
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.connection_crypto import decrypt
from app.core.rate_limit import enforce_rate_limit
from app.core.webhooks import is_authorized, matches_filter
from app.db import get_db
from app.models.trigger import TriggerKind, WorkflowTrigger
from app.tasks.triggers import record_trigger_error, start_triggered_run

router = APIRouter(prefix="/hooks", tags=["Webhooks"])

MAX_BODY_BYTES = 1024 * 1024
# 每個觸發器每分鐘最多 60 次。用觸發器 id 當鍵而不是來源 IP：
# GitHub 從一大池 IP 送出，用 IP 擋不住也分不出來。
RATE_LIMIT_TIMES = 60
RATE_LIMIT_SECONDS = 60
DELIVERY_ID_MAX = 200


async def _read_limited_body(request: Request) -> bytes:
    """在驗證之前就要讀完整個 body（HMAC 是對原始 bytes 算的），所以一定要先限大小。"""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Body too large")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Body too large")
    return bytes(body)


async def _rate_limit(trigger_id: UUID) -> None:
    await enforce_rate_limit(f"ratelimit:hook:{trigger_id}", RATE_LIMIT_TIMES, RATE_LIMIT_SECONDS)


@router.post("/{trigger_id}", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(_rate_limit)])
def receive_hook(
    trigger_id: UUID,
    response: Response,
    body: bytes = Depends(_read_limited_body),
    authorization: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
    idempotency_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    trigger = db.get(WorkflowTrigger, trigger_id)
    # workflow 觸發器沒有 secret、也不該從外面打得到，當成不存在
    if trigger is None or not trigger.enabled or trigger.kind != TriggerKind.WEBHOOK:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")

    if not is_authorized(decrypt(trigger.encrypted_secret), body, authorization, x_hub_signature_256):
        # 不寫 last_error：任何人都打得到這個網址，不能讓陌生人改觸發器的狀態
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret or signature")

    if x_github_event == "ping":
        # GitHub 建好 webhook 會先送一個 ping，body 跟真正的事件長得完全不一樣，
        # 拿去對應輸入只會失敗，在 GitHub 那邊顯示成紅色的 ✗
        response.status_code = status.HTTP_200_OK
        return {"status": "pong"}

    try:
        payload = json.loads(body) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body must be JSON (for GitHub, set Content type to application/json)",
        )
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body must be a JSON object")

    if not matches_filter(payload, trigger.filter or {}):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    delivery_id = (x_github_delivery or idempotency_key or "").strip()[:DELIVERY_ID_MAX] or None
    try:
        workflow, created = start_triggered_run(db, trigger, payload, delivery_id)
    except ValueError as exc:
        record_trigger_error(db, trigger, f"ValueError: {exc}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if not created:
        response.status_code = status.HTTP_200_OK
        return {"workflow_id": str(workflow.id), "duplicate": True}
    return {"workflow_id": str(workflow.id)}
