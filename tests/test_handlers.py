# ---------------------------------------------------
# Coworkify — task handlers that reach the network or parse user data
#
# The SSRF guard is the part that matters most here: http_request,
# fetch_page and notify all take a URL that a workflow author controls, and
# the worker sits next to Postgres, Redis and (when deployed) a cloud
# metadata endpoint. No test touches the network — requests and DNS are
# replaced, and IP literals resolve without a lookup.
# ---------------------------------------------------

from __future__ import annotations

import socket

import pytest

from app.tasks import handler
from app.tasks.handler import (
    _agent_output_model,
    _validate_public_url,
    handle_condition,
    handle_fetch_page,
    handle_http_request,
    handle_input,
    handle_notify,
)

class FakeResponse:
    def __init__(self, status=200, *, json_body=None, text="", headers=None, chunks=None):
        self.status_code = status
        self._json = json_body
        self.text = text
        self.headers = headers or {}
        self._chunks = chunks if chunks is not None else [text.encode()]
        self.encoding = "utf-8"
        self.closed = False

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and "Location" in self.headers

    is_permanent_redirect = False

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json

    def iter_content(self, size):
        return iter(self._chunks)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True


def html_page(body, **kwargs):
    return FakeResponse(200, text=body, headers={"Content-Type": "text/html, charset=utf-8"}, **kwargs)

# --- SSRF -----------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://10.0.0.5/admin",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",   # AWS / GCP metadata
    "http://100.100.100.200/latest/meta-data/",   # Alibaba Cloud metadata (100.64.0.0/10)
    "http://0.0.0.0:8000/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",                 # IPv4-mapped loopback
    "http://[fd00:ec2::254]/",                    # AWS IPv6 metadata
])
def test_internal_addresses_are_refused(url):
    with pytest.raises(ValueError, match="forbidden IP"):
        _validate_public_url(url)

def test_a_hostname_that_resolves_to_internal_ip_is_refused(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [(socket.AF_INET, 0, 0, "", ("10.1.2.3", 0))]
    )
    with pytest.raises(ValueError, match="forbidden IP"):
        _validate_public_url("http://internal.example.com/")

@pytest.mark.parametrize("url", ["ftp://example.com/", "file:///etc/passwd", "gopher://x/"])
def test_only_http_and_https_are_allowed(url):
    with pytest.raises(ValueError, match="http:// or https://"):
        _validate_public_url(url)

def test_a_public_address_is_allowed():
    _validate_public_url("https://93.184.216.34/")

# --- http_request ------------------------------------------------------------------

def test_http_request_does_not_follow_redirects(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, json_body={"ok": True})

    monkeypatch.setattr(handler.requests, "request", fake_request)
    result = handle_http_request({"url": "https://93.184.216.34/api", "method": "post", "body": {"a": 1}})

    assert result == {"status_code": 200, "response_body": {"ok": True}}
    ((method, _, kwargs), ) = calls
    assert method == "POST"
    # 跟著轉址走就能被「第一跳公開、第二跳內網」繞過 SSRF 檢查
    assert kwargs["allow_redirects"] is False
    assert kwargs["json"] == {"a": 1}

def test_http_request_falls_back_to_truncated_text(monkeypatch):
    monkeypatch.setattr(handler.requests, "request", lambda *a, **kw: FakeResponse(200, text="x" * 5000))
    result = handle_http_request({"url": "https://93.184.216.34/"})
    assert result["response_body"] == "x" * 2000

def test_http_request_checks_the_url_before_sending(monkeypatch):
    monkeypatch.setattr(handler.requests, "request", lambda *a, **kw: pytest.fail("must not send"))
    with pytest.raises(ValueError):
        handle_http_request({"url": "http://169.254.169.254/"})

# --- fetch_page --------------------------------------------------------------------

def serve(monkeypatch, pages: dict):
    """把 requests.get 換成依網址回應的假伺服器，回傳被請求過的網址。"""
    requested = []

    def fake_get(url, **kwargs):
        requested.append(url)
        assert kwargs["allow_redirects"] is False
        return pages[url]

    monkeypatch.setattr(handler.requests, "get", fake_get)
    return requested

def test_fetch_page_rechecks_every_redirect_hop(monkeypatch):
    requested = serve(monkeypatch, {
        "https://93.184.216.34/start": FakeResponse(302, headers={"Location": "http://169.254.169.254/latest"}),
    })

    with pytest.raises(ValueError, match="forbidden IP"):
        handle_fetch_page({"url": "https://93.184.216.34/start"})
    # 第二跳在送出之前就被擋下
    assert requested == ["https://93.184.216.34/start"]

def test_fetch_page_follows_safe_relative_redirects(monkeypatch):
    serve(monkeypatch, {
        "https://93.184.216.34/old": FakeResponse(301, headers={"Location": "/new"}),
        "https://93.184.216.34/new": html_page("<title>New</title><p>moved</p>"),
    })
    assert handle_fetch_page({"url": "https://93.184.216.34/old"})["title"] == "New"

def test_fetch_page_gives_up_after_too_many_redirects(monkeypatch):
    loop = FakeResponse(302, headers={"Location": "https://93.184.216.34/loop"})
    serve(monkeypatch, {"https://93.184.216.34/loop": loop})
    with pytest.raises(ValueError, match="Too many redirects"):
        handle_fetch_page({"url": "https://93.184.216.34/loop"})

def test_fetch_page_refuses_non_html(monkeypatch):
    serve(monkeypatch, {"https://93.184.216.34/api": FakeResponse(
        200, text="{}", headers={"Content-Type": "application/json"})})
    with pytest.raises(ValueError, match="Not an HTML page"):
        handle_fetch_page({"url": "https://93.184.216.34/api"})

def test_fetch_page_stops_reading_past_the_size_limit(monkeypatch):
    big = FakeResponse(200, headers={"Content-Type": "text/html"}, chunks=[b"x" * 1024 * 1024] * 3)
    serve(monkeypatch, {"https://93.184.216.34/big": big})
    with pytest.raises(ValueError, match="larger than 2MB"):
        handle_fetch_page({"url": "https://93.184.216.34/big"})

LISTING = """
<html><head><title>Jobs</title><script>tracking()</script></head><body>
  <ul>
    <li class="job"><a href="/jobs/1">Backend</a><span class="co">Acme</span></li>
    <li class="job"><a href="/jobs/2">Frontend</a></li>
    <li class="job"><a href="/jobs/3">Data</a><span class="co">Initech</span></li>
  </ul>
</body></html>
"""

def test_fetch_page_extracts_one_record_per_item(monkeypatch):
    serve(monkeypatch, {"https://93.184.216.34/jobs": html_page(LISTING)})

    items = handle_fetch_page({
        "url": "https://93.184.216.34/jobs",
        "item_selector": "li.job",
        "fields": '{"title": "a", "link": "a @href", "company": ".co"}',
        "max_items": 2,
    })

    assert items == [
        {"title": "Backend", "link": "https://93.184.216.34/jobs/1", "company": "Acme"},
        # 找不到的欄位是 None，不讓整個步驟失敗
        {"title": "Frontend", "link": "https://93.184.216.34/jobs/2", "company": None},
    ]

def test_fetch_page_without_fields_returns_readable_text(monkeypatch):
    serve(monkeypatch, {"https://93.184.216.34/jobs": html_page(LISTING)})

    page = handle_fetch_page({"url": "https://93.184.216.34/jobs"})

    assert page["title"] == "Jobs"
    assert "Backend" in page["text"]
    assert "tracking" not in page["text"]

def test_fetch_page_rejects_fields_that_are_not_a_json_object(monkeypatch):
    serve(monkeypatch, {"https://93.184.216.34/jobs": html_page(LISTING)})
    with pytest.raises(ValueError, match="fields"):
        handle_fetch_page({"url": "https://93.184.216.34/jobs", "fields": '["a"]'})

# --- notify ------------------------------------------------------------------------


WEBHOOK = "https://93.184.216.34/api/webhooks/1/token"


def capture_post(monkeypatch, status=204):
    sent = []

    def fake_post(url, json, timeout):
        sent.append((url, json))
        return FakeResponse(status, text="slow down")

    monkeypatch.setattr(handler.requests, "post", fake_post)
    return sent


def test_notify_builds_a_discord_embed(monkeypatch):
    sent = capture_post(monkeypatch)

    result = handle_notify({
        "webhook_url": WEBHOOK, "title": "T" * 300, "message": {"new": 2},
        "level": "critical", "link": "https://example.com/run",
    })

    ((url, body),) = sent
    (embed,) = body["embeds"]
    assert url == WEBHOOK
    assert len(embed["title"]) == 256
    assert embed["description"] == '{\n  "new": 2\n}'  # dict 轉成看得懂的 JSON
    assert embed["color"] == 0xE74C3C
    assert embed["url"] == "https://example.com/run"
    assert result["delivered"] is True


def test_notify_falls_back_to_the_worker_env(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    sent = capture_post(monkeypatch)
    handle_notify({"message": "hi"})
    assert sent[0][0] == WEBHOOK


def test_notify_without_a_webhook_or_message_fails_clearly(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(ValueError, match="webhook URL"):
        handle_notify({"message": "hi"})
    with pytest.raises(ValueError, match="message"):
        handle_notify({"webhook_url": WEBHOOK, "message": "  "})


def test_notify_refuses_an_internal_webhook(monkeypatch):
    capture_post(monkeypatch)
    with pytest.raises(ValueError, match="forbidden IP"):
        handle_notify({"webhook_url": "http://10.0.0.8/hook", "message": "hi"})


def test_discord_rate_limiting_raises_so_the_task_is_retried(monkeypatch):
    capture_post(monkeypatch, status=429)
    with pytest.raises(RuntimeError, match="rate limited"):
        handle_notify({"webhook_url": WEBHOOK, "message": "hi"})


# --- condition / input / agent output -------------------------------------------------


@pytest.mark.parametrize("operator, left, right, passed", [
    ("eq", 1, 1, True),
    ("gt", 14, 10, True),
    ("lte", 3, 2, False),
    ("contains", ["a", "b"], "b", True),
    ("not_contains", "hello", "z", True),
    ("is_true", True, None, True),
    ("is_true", "true", None, False),   # 字串 "true" 不是 True，避免被模板插值騙過
    ("is_empty", [], None, True),
    ("is_not_empty", {"a": 1}, None, True),
])
def test_condition_operators(operator, left, right, passed):
    result = handle_condition({"operator": operator, "left": left, "right": right})
    assert result["passed"] is passed


def test_condition_without_left_fails_instead_of_quietly_taking_false():
    with pytest.raises(ValueError, match="left is required"):
        handle_condition({"operator": "is_true", "left": ""})


def test_condition_explains_an_impossible_comparison():
    with pytest.raises(ValueError, match="Can't evaluate"):
        handle_condition({"operator": "gt", "left": 3, "right": "10"})


def test_condition_rejects_unknown_operators():
    with pytest.raises(ValueError, match="Unknown operator"):
        handle_condition({"operator": "between", "left": 1})


@pytest.mark.parametrize("data, expected", [
    ({"repo": "x"}, {"repo": "x"}),
    ([1, 2], [1, 2]),
    ('{"repo": "x"}', {"repo": "x"}),
    ("   ", {}),
])
def test_input_accepts_objects_and_json_text(data, expected):
    assert handle_input({"data": data}) == expected


def test_input_rejects_invalid_json():
    with pytest.raises(ValueError, match="JSON"):
        handle_input({"data": "{not json"})


def test_agent_output_fields_become_a_strict_model():
    Model = _agent_output_model({"fixable": "boolean", "effort": ["small", "large"], "reason": "string"})

    ok = Model(fixable=True, effort="small", reason="typo")
    assert ok.model_dump() == {"fixable": True, "effort": "small", "reason": "typo"}
    with pytest.raises(Exception):
        Model(fixable=True, effort="huge", reason="x")


@pytest.mark.parametrize("spec", [
    {"bad name": "string"},
    {"effort": []},
    {"score": "float"},
])
def test_agent_output_fields_reject_unsupported_specs(spec):
    with pytest.raises(ValueError):
        _agent_output_model(spec)