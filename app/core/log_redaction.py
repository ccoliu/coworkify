import logging
import re

# 瀏覽器的 WebSocket 不能帶 Authorization header，JWT 只能放在 /ws/tasks?token=... 裡，
# 而 uvicorn 會把完整網址（含 query string）寫進 log。不遮掉的話，任何拿得到 log 的人
# 都能拿 token 冒用那個使用者，直到它過期（7 天）。
_TOKEN_IN_URL = re.compile(r"((?:^|[?&])(?:access_)?token=)[^&\s\"']+")

# WebSocket 握手那幾行是 uvicorn.error 印的，一般 HTTP 請求是 uvicorn.access
UVICORN_LOGGERS = ("uvicorn.access", "uvicorn.error")


def redact_tokens(text:str) -> str:
    return _TOKEN_IN_URL.sub(r"\1<redacted>", text)

class RedactTokenFilter(logging.Filter):
    """把 log 訊息裡網址上的 token=... 換成 token=<redacted>，其餘內容不動。"""


    def filter(self, record: logging.LogRecord) -> bool:
        # 只改 args 裡的字串，保留 args 的形狀：uvicorn 的 AccessFormatter 會依位置
        # 讀 args（status code 拿來上色），整個清空會讓它格式化失敗。
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_tokens(a) if isinstance(a, str) and "token=" in a else a for a in record.args
            )
        if isinstance(record.msg, str) and "token=" in record.msg:
            record.msg = redact_tokens(record.msg)
        return True

def install_token_redaction() -> None:
    redaction = RedactTokenFilter()
    for name in UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        # --reload 會重新 import app，避免同一個 logger 掛上好幾個 filter
        if not any(isinstance(h, RedactTokenFilter) for h in logger.filters):
            logger.addFilter(redaction)