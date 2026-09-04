from datetime import datetime
from zoneinfo import ZoneInfo
from croniter import croniter

APP_TZ = ZoneInfo("Asia/Taipei")  # 跟 celery_app.py 的 timezone 設定保持一致


def compute_next_run(cron_expression: str, base_utc: datetime) -> datetime:
    """cron 表達式以 APP_TZ（台灣時間）為準解讀，回傳 naive UTC datetime 供 DB 儲存與比較"""
    base_local = base_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(APP_TZ)
    next_local = croniter(cron_expression, base_local).get_next(datetime)
    return next_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
