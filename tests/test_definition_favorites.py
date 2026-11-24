"""
常用（星號）定義：建構器的 Workflows 選單先載入這些，其他的要用時才抓。
"""
import uuid

from app.models.workflow import WorkflowDefinition

STEPS = [{"key": "hello", "name": "hello", "task_type": "echo", "payload": {"message": "hi"}, "priority": 3}]


def make_definition(client, auth, name) -> str:
    res = client.post("/definitions/", json={"name": name, "steps": STEPS, "input_schema": []}, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def names(res) -> set[str]:
    assert res.status_code == 200, res.text
    return {d["name"] for d in res.json()}


def test_a_new_definition_is_not_a_favorite(client, auth):
    def_id = make_definition(client, auth, "plain")
    assert client.get(f"/definitions/{def_id}", headers=auth).json()["is_favorite"] is False


def test_favoriting_and_unfavoriting(client, auth):
    def_id = make_definition(client, auth, "daily")

    res = client.put(f"/definitions/{def_id}/favorite", headers=auth)
    assert res.status_code == 200 and res.json()["is_favorite"] is True
    # 重複標沒有副作用
    assert client.put(f"/definitions/{def_id}/favorite", headers=auth).json()["is_favorite"] is True

    res = client.delete(f"/definitions/{def_id}/favorite", headers=auth)
    assert res.status_code == 200 and res.json()["is_favorite"] is False


def test_favoriting_does_not_count_as_an_edit(client, auth, db):
    def_id = make_definition(client, auth, "daily")
    before = client.get(f"/definitions/{def_id}", headers=auth).json()

    after = client.put(f"/definitions/{def_id}/favorite", headers=auth).json()

    assert after["version"] == before["version"]
    assert after["updated_at"] == before["updated_at"]


def test_the_list_can_be_split_into_favorites_and_the_rest(client, auth):
    fav = make_definition(client, auth, "fav")
    make_definition(client, auth, "other")
    client.put(f"/definitions/{fav}/favorite", headers=auth)

    assert names(client.get("/definitions/", params={"favorite": "true"}, headers=auth)) == {"fav"}
    assert names(client.get("/definitions/", params={"favorite": "false"}, headers=auth)) == {"other"}
    assert names(client.get("/definitions/", headers=auth)) == {"fav", "other"}


def test_someone_elses_definition_cannot_be_favorited(client, auth, other_auth, db):
    def_id = make_definition(client, auth, "mine")

    assert client.put(f"/definitions/{def_id}/favorite", headers=other_auth).status_code == 404
    assert client.delete(f"/definitions/{def_id}/favorite", headers=other_auth).status_code == 404
    assert db.get(WorkflowDefinition, uuid.UUID(def_id)).is_favorite is False


def test_saving_a_definition_keeps_its_star(client, auth):
    def_id = make_definition(client, auth, "daily")
    client.put(f"/definitions/{def_id}/favorite", headers=auth)

    res = client.put(f"/definitions/{def_id}", json={"name": "daily v2", "steps": STEPS, "input_schema": []}, headers=auth)

    assert res.json()["is_favorite"] is True
