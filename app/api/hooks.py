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
- 404：觸發器不存在或停用
- 422：取出來的輸入不合定義的 input_schema（也會記在觸發器的 last_error）
"""
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.connection_crypto import decrypt
from app.core.rate_limit import enforce_rate_limit
from app.core.webhooks import extract_input, is_authorized, matches_filter
from app.db import get_db
from app.models.trigger import WorkflowTrigger
from app.models.workflow import Workflow, WorkflowDefinition
from app.schemas.definition import resolve_run_input
from app.tasks.executor import create_workflow_from_steps

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


def _existing_run(db: Session, trigger_id: UUID, delivery_id: str) -> Workflow | None:
    return db.scalars(
        select(Workflow).where(Workflow.trigger_id == trigger_id, Workflow.trigger_delivery_id == delivery_id)
    ).first()


def _record_error(db: Session, trigger: WorkflowTrigger, message: str) -> None:
    trigger.last_error = message
    trigger.last_error_at = datetime.utcnow()
    db.commit()


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
    if trigger is None or not trigger.enabled:
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
    if delivery_id:
        existing = _existing_run(db, trigger.id, delivery_id)
        if existing:
            response.status_code = status.HTTP_200_OK
            return {"workflow_id": str(existing.id), "duplicate": True}

    definition = db.get(WorkflowDefinition, trigger.definition_id)
    if definition.input_schema:
        try:
            run_input = resolve_run_input(definition.input_schema, extract_input(payload, trigger.input_mapping or {}))
        except ValueError as exc:
            _record_error(db, trigger, f"ValueError: {exc}")
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    else:
        run_input = None

    try:
        workflow = create_workflow_from_steps(
            db,
            definition.name,
            definition.steps,
            definition_id=definition.id,
            definition_version=definition.version,
            run_input=run_input,
            created_by=trigger.created_by,
            trigger_kind="webhook",
            trigger_id=trigger.id,
            trigger_delivery_id=delivery_id,
        )
    except IntegrityError:
        # 同一個 delivery 的兩份請求同時通過了上面的檢查，unique constraint 擋下後到的那份
        db.rollback()
        existing = _existing_run(db, trigger.id, delivery_id) if delivery_id else None
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return {"workflow_id": str(existing.id), "duplicate": True}
    except ValueError as exc:
        # 定義本身有問題（例如 for_each 指向不存在的 step）
        db.rollback()
        _record_error(db, trigger, f"ValueError: {exc}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    trigger.last_triggered_at = datetime.utcnow()
    trigger.last_error = None
    trigger.last_error_at = None
    db.commit()
    return {"workflow_id": str(workflow.id)}
