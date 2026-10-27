# ---------------------------------------------------
# Coworkify — JWTs must not end up in the server log
#
# /ws/tasks takes its JWT in the query string (browsers can't set headers on
# a WebSocket), and uvicorn logs the full URL of every handshake. These run
# records through the real uvicorn loggers, in the exact format uvicorn's
# WebSocket and HTTP protocols use.
# ---------------------------------------------------

from __future__ import annotations

import logging

import pytest

import app.main  # noqa: F401  匯入 app 就會掛上過濾器
from app.core.log_redaction import redact_tokens

JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl"


@pytest.mark.parametrize("logger_name, msg, args", [
    # uvicorn/protocols/websockets/websockets_impl.py
    ("uvicorn.error", '%s - "WebSocket %s" [accepted]', ("172.19.0.4:43486", f"/ws/tasks?token={JWT}")),
    ("uvicorn.error", '%s - "WebSocket %s" 403', ("172.19.0.4:43486", f"/ws/tasks?token={JWT}")),
    # uvicorn/protocols/http/h11_impl.py
    ("uvicorn.access", '%s - "%s %s HTTP/%s" %d',
     ("172.19.0.4:1234", "GET", f"/tasks/?limit=20&token={JWT}&offset=0", "1.1", 200)),
])
def test_uvicorn_never_logs_a_token(caplog, logger_name, msg, args):
    with caplog.at_level(logging.INFO, logger=logger_name):
        logging.getLogger(logger_name).info(msg, *args)
    
    (record, ) = caplog.records
    assert JWT not in record.getMessage()
    assert "token=<redacted>" in record.getMessage()


def test_the_rest_of_the_line_is_untouched():
    line = f'172.19.0.4:1 - "GET /tasks/?limit=20&token={JWT}&offset=0 HTTP/1.1" 200'
    assert redact_tokens(line) == '172.19.0.4:1 - "GET /tasks/?limit=20&token=<redacted>&offset=0 HTTP/1.1" 200'

def test_lines_without_a_token_are_left_alone(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        logging.getLogger("uvicorn.error").info('%s - "WebSocket %s" 403', "1.2.3.4:5", "/ws/tasks")
    assert caplog.records[0].getMessage() == '1.2.3.4:5 - "WebSocket /ws/tasks" 403'
    
def test_uvicorns_access_formatter_still_works_after_redaction():
    # AccessFormatter 依位置讀 args（client、method、path、HTTP 版本、status code），
    # 過濾器要是把 args 清空，格式化會直接丟例外——caplog 用的是自己的格式器，看不出來
    from uvicorn.logging import AccessFormatter

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d',
        ("172.19.0.4:1234", "GET", f"/health?token={JWT}", "1.1", 200), None,
    )
    for f in logging.getLogger("uvicorn.access").filters:
        f.filter(record)

    line = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False).format(record)
    assert line == '172.19.0.4:1234 - "GET /health?token=<redacted> HTTP/1.1" 200 OK'