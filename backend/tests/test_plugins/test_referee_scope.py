"""todo 7: per-competition referee scope on the gameplay-log import endpoint（④A 越权堵漏）。

玩法路由已从对局流程解耦，原 /api/gameplay/<name>/session 等端点不复存在；
其"比赛级裁判归属"校验语义由 gameplay-log 导入端点继承 —— referee 必须在该
比赛的 referee_ids 内才能导入日志，admin 始终放行。

覆盖：POST /api/matches/{id}/gameplay-log ×
（未指派裁判 403 / 指派裁判 200 / admin 200 / player 403 / 未知对局 404）。
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.competition import Competition
from app.models.match import Match
from app.models.user import User

PASSWORD = "secret123"

SAMPLE_EVENTS = [
    {"time": "00:32", "text": "守护者占领了L2第1个格子 (8) [守卫]", "type": "occupy"},
    {"time": "12:30", "text": "游戏结束 — 时间到，守护者获胜（积分 85:72）", "type": "victory"},
]


def _flip_role(username: str, role: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        user.role = role
        db.commit()


def _role_client(username: str, role: str) -> TestClient:
    c = TestClient(app)
    resp = c.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 200
    _flip_role(username, role)
    return c


@pytest.fixture()
def env() -> dict:
    """Fresh DB：指派比赛（assigned 裁判在 referee_ids）+ 未指派比赛（空裁判
    组），各带一张 in_progress 对局。返回 admin/assigned/outsider/player
    客户端与两张对局的对局 id。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app):
        admin = _role_client("scope_admin", "admin")
        assigned = _role_client("scope_assigned", "referee")
        outsider = _role_client("scope_outsider", "referee")
        player = _role_client("scope_player", "player")
        with SessionLocal() as db:
            admin_id = db.query(User).filter(User.username == "scope_admin").one().id
            assigned_id = db.query(User).filter(User.username == "scope_assigned").one().id
            comp_a = Competition(
                name="指派比赛", status="ongoing", created_by=admin_id, referee_ids=[assigned_id]
            )
            db.add(comp_a)
            db.flush()
            match_a = Match(
                competition_id=comp_a.id,
                round_id=1,
                participant_a=101,
                participant_b=102,
                engine_match_id=1,
                status="in_progress",
            )
            db.add(match_a)
            comp_b = Competition(
                name="未指派比赛", status="ongoing", created_by=admin_id, referee_ids=[]
            )
            db.add(comp_b)
            db.flush()
            match_b = Match(
                competition_id=comp_b.id,
                round_id=1,
                participant_a=201,
                participant_b=202,
                engine_match_id=1,
                status="in_progress",
            )
            db.add(match_b)
            db.commit()
            match_a_id, match_b_id = match_a.id, match_b.id
        yield {
            "admin": admin,
            "assigned": assigned,
            "outsider": outsider,
            "player": player,
            "assigned_match_id": match_a_id,
            "unassigned_match_id": match_b_id,
        }


def _import(client: TestClient, match_id: int) -> TestClient:
    return client.post(
        f"/api/matches/{match_id}/gameplay-log",
        files={
            "file": (
                "events.json",
                json.dumps(SAMPLE_EVENTS).encode("utf-8"),
                "application/json",
            )
        },
    )


def test_import_outsider_referee_403(env):
    """全局 referee（不在 referee_ids）不能为他人比赛导入日志。"""
    resp = _import(env["outsider"], env["assigned_match_id"])
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_import_assigned_referee_200(env):
    resp = _import(env["assigned"], env["assigned_match_id"])
    assert resp.status_code == 200, resp.text


def test_import_admin_on_unassigned_200(env):
    resp = _import(env["admin"], env["unassigned_match_id"])
    assert resp.status_code == 200, resp.text


def test_import_player_forbidden_403(env):
    resp = _import(env["player"], env["assigned_match_id"])
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_import_unknown_match_404(env):
    resp = _import(env["assigned"], 99999)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "对局不存在"
