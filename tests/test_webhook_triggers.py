# ---------------------------------------------------
# Coworkify — webhook triggers (issue #9, phase 1)
#
# What has to hold:
#   - POST /hooks/{id} starts a run without a user JWT, authenticated by the
#     trigger's own secret: a Bearer token or GitHub's X-Hub-Signature-256;
#   - the secret is encrypted at rest and only returned on create / rotate;
#   - only mapped fields reach the run, validated against the input_schema;
#   - a filter that doesn't match creates nothing (204);
#   - a redelivered delivery id returns the first run instead of a second one;
#   - an unknown or disabled trigger is 404, and failures after auth are
#     kept on the trigger as last_error.
# ---------------------------------------------------

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.api import hooks
from app.core.webhooks import extract_input, is_authorized, matches_filter
from app.models.trigger import WorkflowTrigger
from app.models.workflow import Workflow

STEPS = [{"key": "input_1", "name": "input", "task_type": "input", "payload": {}, "priority": 3}]
SCHEMA = [
    {"key": "repo", "label": "Repository", "kind": "string", "required": True},
    {"key": "number", "label": "Issue number", "kind": "number", "required": False},
]
ISSUE_OPENED = {
    "action": "opened",
    "issue": {"number": 12, "title": "Crash on start"},
    "repository": {"full_name": "ccoliu/coworkify"},
}


@pytest.fixture(autouse=True)
def connections_key(monkeypatch):
    monkeypatch.setenv("CONNECTIONS_KEY", Fernet.generate_key().decode())


@pytest.fixture
def definition_id(client, auth):
    res = client.post(
        "/definitions/", json={"name": "triage", "steps": STEPS, "input_schema": SCHEMA}, headers=auth
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture
def trigger(client, auth, definition_id):
    res = client.post(
        "/triggers/",
        json={
            "name": "github issues",
            "definition_id": definition_id,
            "input_mapping": {"repo": "repository.full_name", "number": "issue.number"},
            "filter": {"action": "opened"},
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return res.json()


def bearer(trigger) -> dict:
    return {"Authorization": f"Bearer {trigger['secret']}"}


def github_headers(trigger, body: bytes, **extra) -> dict:
    digest = hmac.new(trigger["secret"].encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}", "Content-Type": "application/json", **extra}


def runs(db) -> list[Workflow]:
    db.expire_all()
    return db.scalars(select(Workflow)).all()


def reload_trigger(db, trigger) -> WorkflowTrigger:
    db.expire_all()
    return db.get(WorkflowTrigger, trigger["id"])


# --- pure helpers ------------------------------------------------------------------


def test_bearer_and_signature_are_both_accepted():
    body = b'{"a": 1}'
    signature = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert is_authorized("s3cret", body, "Bearer s3cret", None)
    assert is_authorized("s3cret", body, None, signature)


@pytest.mark.parametrize(
    "authorization, signature",
    [
        (None, None),
        ("Bearer wrong", None),
        ("Basic s3cret", None),
        # 簽章優先：帶了錯的簽章，就算 Bearer 對也不放行
        ("Bearer s3cret", "sha256=" + "0" * 64),
        (None, "sha1=abc"),
    ],
)
def test_anything_else_is_rejected(authorization, signature):
    assert not is_authorized("s3cret", b"{}", authorization, signature)


def test_the_signature_covers_the_exact_body():
    signature = "sha256=" + hmac.new(b"s3cret", b'{"a": 1}', hashlib.sha256).hexdigest()
    assert not is_authorized("s3cret", b'{"a": 2}', None, signature)


def test_filter_is_type_sensitive_and_lists_mean_any_of():
    body = {"action": "opened", "count": 1, "flag": True}
    assert matches_filter(body, {"action": ["opened", "reopened"]})
    assert matches_filter(body, {})
    assert not matches_filter(body, {"count": "1"})
    assert not matches_filter(body, {"flag": 1})
    assert not matches_filter(body, {"missing": None})


def test_extract_input_only_takes_mapped_paths_that_exist():
    assert extract_input(ISSUE_OPENED, {"repo": "repository.full_name", "x": "nope.nope"}) == {
        "repo": "ccoliu/coworkify"
    }


# --- managing triggers -------------------------------------------------------------


def test_the_secret_is_encrypted_and_returned_only_once(client, auth, trigger, db):
    stored = reload_trigger(db, trigger)
    assert trigger["secret"] not in stored.encrypted_secret
    assert trigger["hook_path"] == f"/hooks/{trigger['id']}"

    listed = client.get("/triggers/", headers=auth).json()
    assert [t["id"] for t in listed] == [trigger["id"]]
    assert "secret" not in listed[0]
    assert "secret" not in client.get(f"/triggers/{trigger['id']}", headers=auth).json()


def test_mapping_to_an_undeclared_field_is_rejected(client, auth, definition_id):
    res = client.post(
        "/triggers/",
        json={"name": "typo", "definition_id": definition_id, "input_mapping": {"rpeo": "repository.full_name"}},
        headers=auth,
    )
    assert res.status_code == 400
    assert "rpeo" in res.json()["detail"]


def test_someone_elses_definition_or_trigger_is_off_limits(client, auth, other_auth, definition_id, trigger):
    res = client.post("/triggers/", json={"name": "x", "definition_id": definition_id}, headers=other_auth)
    assert res.status_code == 400
    assert client.get(f"/triggers/{trigger['id']}", headers=other_auth).status_code == 404
    assert client.delete(f"/triggers/{trigger['id']}", headers=other_auth).status_code == 404


def test_rotating_the_secret_invalidates_the_old_one(client, auth, trigger):
    rotated = client.post(f"/triggers/{trigger['id']}/rotate-secret", headers=auth).json()
    assert rotated["secret"] != trigger["secret"]

    old = client.post(trigger["hook_path"], json=ISSUE_OPENED, headers=bearer(trigger))
    new = client.post(trigger["hook_path"], json=ISSUE_OPENED, headers=bearer(rotated))
    assert old.status_code == 401
    assert new.status_code == 202


# --- receiving webhooks ------------------------------------------------------------


def test_a_bearer_call_starts_a_run_with_only_the_mapped_input(client, trigger, db):
    res = client.post(trigger["hook_path"], json=ISSUE_OPENED, headers=bearer(trigger))

    assert res.status_code == 202, res.text
    [run] = runs(db)
    assert str(run.id) == res.json()["workflow_id"]
    assert run.input == {"repo": "ccoliu/coworkify", "number": 12}
    assert run.trigger_kind == "webhook"
    assert str(run.trigger_id) == trigger["id"]
    # run 屬於觸發器的擁有者，不是匿名的
    assert run.created_by == reload_trigger(db, trigger).created_by
    assert client.dispatched, "the root step should have been dispatched"
    assert reload_trigger(db, trigger).last_triggered_at is not None


def test_a_github_signed_delivery_starts_a_run(client, trigger, db):
    body = json.dumps(ISSUE_OPENED).encode()
    res = client.post(
        trigger["hook_path"], content=body, headers=github_headers(trigger, body, **{"X-GitHub-Event": "issues"})
    )
    assert res.status_code == 202, res.text
    assert len(runs(db)) == 1


def test_github_ping_is_answered_without_a_run(client, trigger, db):
    body = json.dumps({"zen": "Keep it logically awesome.", "hook_id": 1}).encode()
    res = client.post(
        trigger["hook_path"], content=body, headers=github_headers(trigger, body, **{"X-GitHub-Event": "ping"})
    )
    assert res.status_code == 200
    assert res.json() == {"status": "pong"}
    assert runs(db) == []


def test_a_bad_secret_is_401_and_leaves_no_trace(client, trigger, db):
    res = client.post(trigger["hook_path"], json=ISSUE_OPENED, headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401
    assert runs(db) == []
    assert reload_trigger(db, trigger).last_error is None


def test_unknown_and_disabled_triggers_are_404(client, auth, trigger):
    unknown = client.post("/hooks/00000000-0000-0000-0000-000000000000", json={}, headers=bearer(trigger))
    assert unknown.status_code == 404

    client.patch(f"/triggers/{trigger['id']}", json={"enabled": False}, headers=auth)
    disabled = client.post(trigger["hook_path"], json=ISSUE_OPENED, headers=bearer(trigger))
    assert disabled.status_code == 404


def test_a_non_matching_filter_creates_nothing(client, trigger, db):
    res = client.post(trigger["hook_path"], json={**ISSUE_OPENED, "action": "closed"}, headers=bearer(trigger))
    assert res.status_code == 204
    assert runs(db) == []


def test_a_redelivery_returns_the_first_run(client, trigger, db):
    body = json.dumps(ISSUE_OPENED).encode()
    headers = github_headers(trigger, body, **{"X-GitHub-Delivery": "72d3162e-cc78-11e3-81ab-4c9367dc0958"})

    first = client.post(trigger["hook_path"], content=body, headers=headers)
    again = client.post(trigger["hook_path"], content=body, headers=headers)

    assert first.status_code == 202
    assert again.status_code == 200
    assert again.json() == {"workflow_id": first.json()["workflow_id"], "duplicate": True}
    assert len(runs(db)) == 1


def test_different_deliveries_and_missing_delivery_ids_each_start_a_run(client, trigger, db):
    for delivery in ("a", "b", None, None):
        headers = bearer(trigger) | ({"Idempotency-Key": delivery} if delivery else {})
        assert client.post(trigger["hook_path"], json=ISSUE_OPENED, headers=headers).status_code == 202
    assert len(runs(db)) == 4


def test_input_that_fails_the_schema_is_422_and_kept_as_last_error(client, trigger, db):
    without_repo = {"action": "opened", "issue": {"number": 12}}
    res = client.post(trigger["hook_path"], json=without_repo, headers=bearer(trigger))

    assert res.status_code == 422
    assert runs(db) == []
    stored = reload_trigger(db, trigger)
    assert "Repository" in stored.last_error
    assert stored.last_triggered_at is None

    # 下一次成功就清掉
    assert client.post(trigger["hook_path"], json=ISSUE_OPENED, headers=bearer(trigger)).status_code == 202
    assert reload_trigger(db, trigger).last_error is None


@pytest.mark.parametrize("body", [b"payload=%7B%7D", b"[1, 2]"])
def test_a_body_that_is_not_a_json_object_is_400(client, trigger, body):
    res = client.post(trigger["hook_path"], content=body, headers=bearer(trigger))
    assert res.status_code == 400


def test_an_oversized_body_is_413(client, trigger, monkeypatch):
    monkeypatch.setattr(hooks, "MAX_BODY_BYTES", 100)
    res = client.post(trigger["hook_path"], content=b"x" * 101, headers=bearer(trigger))
    assert res.status_code == 413


def test_the_hook_is_rate_limited(client, trigger):
    client.fake_redis.requests_in_window = hooks.RATE_LIMIT_TIMES
    res = client.post(trigger["hook_path"], json=ISSUE_OPENED, headers=bearer(trigger))
    assert res.status_code == 429


def test_deleting_the_definition_removes_its_triggers(definition_id, trigger, db):
    from app.models.workflow import WorkflowDefinition

    # 定義 API 沒有 DELETE，直接在 DB 刪：驗的是 FK 的 ON DELETE CASCADE
    db.delete(db.get(WorkflowDefinition, definition_id))
    db.commit()
    assert reload_trigger(db, trigger) is None
