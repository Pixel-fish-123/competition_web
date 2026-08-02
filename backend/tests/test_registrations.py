"""TDD tests for the registration endpoints (individual / team / capacity).

Competition rows are created directly via ``SessionLocal`` — the full
Competition admin CRUD is todo 8, so tests seed the minimal placeholder model.

Multi-user scenarios use a single TestClient whose cookie jar is swapped
between users (register auto-logs-in and sets the "token" cookie), exactly
like tests/test_teams.py.
"""

from app.db import SessionLocal
from app.models.competition import Competition

PASSWORD = "secret123"


def _register(client, username, email):
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"], client.cookies.get("token")


def _as_user(client, token):
    client.cookies.set("token", token)


def _create_competition(
    name="测试比赛",
    max_participants=50,
    status="registration",
    participant_type="mixed",
):
    with SessionLocal() as db:
        comp = Competition(
            name=name,
            max_participants=max_participants,
            status=status,
            participant_type=participant_type,
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)
        return comp.id


def _register_individual(client, competition_id):
    return client.post(
        f"/api/competitions/{competition_id}/register",
        json={"participant_type": "individual"},
    )


def test_individual_register_success(client):
    user_id, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()

    resp = _register_individual(client, comp_id)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert data["user_id"] == user_id
    assert data["participant_type"] == "individual"
    assert data["competition_id"] == comp_id
    assert data["team_id"] is None
    # approved_by is an internal DB field, deliberately not exposed yet.
    assert "approved_by" not in data


def test_duplicate_individual_register_returns_400(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()

    assert _register_individual(client, comp_id).status_code == 200
    resp = _register_individual(client, comp_id)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "已报名"


def test_team_register_captain_only_and_once(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")
    comp_id = _create_competition()

    _as_user(client, a_token)
    team_id = client.post("/api/teams", json={"name": "队伍A"}).json()["id"]
    assert (
        client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code
        == 200
    )

    # Captain registers the team -> 200, user_id is the captain's id.
    resp = client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team", "team_id": team_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == a_id
    assert resp.json()["team_id"] == team_id
    assert resp.json()["participant_type"] == "team"

    # Same team again -> 400.
    resp = client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team", "team_id": team_id},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该队伍已报名"

    # Non-captain member tries to register the team -> 403.
    _as_user(client, b_token)
    resp = client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team", "team_id": team_id},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "只有队长可以报名"

    # Team member has no personal registration row (covered via team).
    resp = client.get("/api/my/registrations")
    assert resp.status_code == 200
    assert resp.json()["registrations"] == []


def test_team_register_missing_team_id_returns_422(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()

    resp = client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team"},
    )
    assert resp.status_code == 422


def test_team_register_unknown_team_returns_404(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()

    resp = client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team", "team_id": 9999},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "队伍不存在"


def test_competition_not_in_registration_returns_400(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition(status="draft")

    resp = _register_individual(client, comp_id)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "当前不可报名"


def test_register_unknown_competition_returns_404(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)

    resp = _register_individual(client, 9999)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "比赛不存在"


def test_capacity_full_returns_400(client):
    _, a_token = _register(client, "user_a", "a@example.com")
    _, b_token = _register(client, "user_b", "b@example.com")
    comp_id = _create_competition(max_participants=1)

    _as_user(client, a_token)
    assert _register_individual(client, comp_id).status_code == 200

    _as_user(client, b_token)
    resp = _register_individual(client, comp_id)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "报名已满"


def test_withdraw_individual_then_reregister(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()

    assert _register_individual(client, comp_id).status_code == 200

    resp = client.delete(f"/api/competitions/{comp_id}/register")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    # Slot freed -> can register again.
    assert _register_individual(client, comp_id).status_code == 200


def test_withdraw_team_captain(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")
    comp_id = _create_competition()

    _as_user(client, a_token)
    team_id = client.post("/api/teams", json={"name": "队伍A"}).json()["id"]
    assert (
        client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/competitions/{comp_id}/register",
            json={"participant_type": "team", "team_id": team_id},
        ).status_code
        == 200
    )

    resp = client.delete(f"/api/competitions/{comp_id}/register")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    # Captain can register the team again after withdrawing.
    resp = client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team", "team_id": team_id},
    )
    assert resp.status_code == 200, resp.text


def test_withdraw_when_finished_returns_400(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()
    assert _register_individual(client, comp_id).status_code == 200

    with SessionLocal() as db:
        comp = db.get(Competition, comp_id)
        comp.status = "finished"
        db.commit()

    resp = client.delete(f"/api/competitions/{comp_id}/register")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "比赛已结束，无法撤销"


def test_withdraw_without_registration_returns_404(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()

    resp = client.delete(f"/api/competitions/{comp_id}/register")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "报名记录不存在"


def test_register_unauthenticated_returns_401(client):
    comp_id = _create_competition()
    resp = _register_individual(client, comp_id)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_list_registrations_for_competition(client):
    user_id, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()
    assert _register_individual(client, comp_id).status_code == 200

    resp = client.get(f"/api/competitions/{comp_id}/registrations")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["user_id"] == user_id
    assert rows[0]["competition_id"] == comp_id
    assert rows[0]["status"] == "pending"


def test_my_registrations(client):
    user_id, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    comp_id = _create_competition()
    assert _register_individual(client, comp_id).status_code == 200

    resp = client.get("/api/my/registrations")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["registrations"]
    assert len(rows) == 1
    assert rows[0]["user_id"] == user_id
    assert rows[0]["competition_id"] == comp_id


def test_my_registrations_empty_when_none(client):
    _, token = _register(client, "user_a", "a@example.com")
    _as_user(client, token)
    _create_competition()

    resp = client.get("/api/my/registrations")
    assert resp.status_code == 200
    assert resp.json()["registrations"] == []
