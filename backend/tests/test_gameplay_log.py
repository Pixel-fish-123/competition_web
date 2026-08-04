"""TDD tests for the gameplay-log import endpoint（todo：玩法日志导入）。

覆盖：
- POST /api/matches/{id}/gameplay-log（JSON/CSV 上传）→ 200，
  match.gameplay_log 填充 events + 从 victory 事件解析出的比分/胜者。
- GET /api/matches/{id}/gameplay-log 读回已存日志；MatchOut 亦带 gameplay_log。
- 表单字段 score_a/score_b/winner 显式覆盖解析值。
- ?sync=true → 预填 match.result（不结束对局、不触碰引擎）。
- 重复导入覆盖旧日志（幂等）；坏文件/空文件 400 且错误清晰。
"""

import json

from app.db import SessionLocal
from app.models.match import Match
from app.models.registration import Registration
from app.models.user import User

PASSWORD = "secret123"

SONG_LIB = {
    "songs": [
        {"name": f"歌曲{i:02d}", "type": "Glitch", "level": f"{i % 10 + 6}"}
        for i in range(1, 24)
    ]
}

BASE_PAYLOAD = {
    "name": "玩法日志测试比赛",
    "description": "玩法日志导入测试",
    "participant_type": "individual",
    "tournament_format": "round_robin",
    "format_config": {"group_size": 6},
    "points_rule": {"1": 10, "2": 5},
    "gameplay_plugin": "triangle_occupy",
    "song_lib": SONG_LIB,
    "referee_ids": [],
    "max_participants": 6,
}

# demo 导出的 JSON 事件数组（victory 事件含比分与胜者）。
SAMPLE_EVENTS = [
    {"time": "00:32", "text": "守护者占领了L2第1个格子 的SongName 任务名 (8) [守卫]", "type": "occupy"},
    {"time": "01:15", "text": "掠夺者占领了L1源头 (固定+10) 的SongName L1源头 (15) [占领L1]", "type": "l1"},
    {"time": "12:30", "text": "游戏结束 — 时间到，守护者获胜（积分 85:72）", "type": "victory"},
]

# demo 导出的 CSV（BOM + time,type,text 表头）。
SAMPLE_CSV = (
    "\ufefftime,type,text\n"
    "00:32,occupy,守护者占领了L2第1个格子 的SongName 任务名 (8) [守卫]\n"
    "12:30,victory,游戏结束 — 时间到，掠夺者获胜（积分 72:85）\n"
)


def _register(client, username, email):
    client.cookies.clear()
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"], client.cookies.get("token")


def _as_user(client, token):
    client.cookies.clear()
    client.cookies.set("token", token)


def _make_referee(client, admin_token, username="log_referee", email="log_referee@example.com"):
    referee_id, referee_token = _register(client, username, email)
    _as_user(client, admin_token)
    with SessionLocal() as db:
        user = db.get(User, referee_id)
        user.role = "referee"
        db.commit()
    return referee_id, referee_token


def _seed(admin_client):
    """Create round-robin competition with 6 approved players -> ongoing;
    return (first_match_id, referee_token)."""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    payload = {**BASE_PAYLOAD, "referee_ids": [referee_id]}
    resp = admin_client.post("/api/competitions", json=payload)
    assert resp.status_code == 200, resp.text
    comp_id = resp.json()["id"]

    assert (
        admin_client.post(f"/api/competitions/{comp_id}/status", json={"status": "registration"}).status_code
        == 200
    )
    for i in range(6):
        pid, ptoken = _register(admin_client, f"log_player_{i}", f"log_player{i}@example.com")
        _as_user(admin_client, ptoken)
        resp = admin_client.post(
            f"/api/competitions/{comp_id}/register",
            json={"participant_type": "individual"},
        )
        assert resp.status_code == 200, resp.text
    _as_user(admin_client, admin_token)
    with SessionLocal() as db:
        regs = db.query(Registration).filter(Registration.competition_id == comp_id).all()
        assert len(regs) == 6
        for reg in regs:
            reg.status = "approved"
        db.commit()
    assert (
        admin_client.post(f"/api/competitions/{comp_id}/status", json={"status": "ongoing"}).status_code
        == 200
    )
    matches = admin_client.get(f"/api/competitions/{comp_id}/matches").json()
    assert matches
    return matches[0]["id"], referee_token


def _start(admin_client, match_id, referee_token):
    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{match_id}/start", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "in_progress"


def _upload(admin_client, match_id, *, content, filename="events.json", **extra):
    return admin_client.post(
        f"/api/matches/{match_id}/gameplay-log",
        files={"file": (filename, content, "application/json")},
        **extra,
    )


# ------------------------------------------------------------------- JSON


def test_import_json_log_populates_gameplay_log(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = _upload(
        admin_client,
        match_id,
        content=json.dumps(SAMPLE_EVENTS).encode("utf-8"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["match_id"] == match_id
    log = body["gameplay_log"]
    assert len(log["events"]) == 3
    assert log["events"][0]["type"] == "occupy"
    assert log["events"][2]["type"] == "victory"
    # 从最后一条 victory 事件解析比分与胜者（守护者=defender=participant_a）。
    assert log["scores"] == {"defender": 85.0, "attacker": 72.0}
    assert log["winner"] == "defender"
    assert "imported_at" in log

    # GET 读回；MatchOut 也带 gameplay_log。
    get = admin_client.get(f"/api/matches/{match_id}/gameplay-log")
    assert get.status_code == 200
    assert get.json()["gameplay_log"]["winner"] == "defender"
    detail = admin_client.get(f"/api/matches/{match_id}")
    assert detail.status_code == 200
    assert detail.json()["match"]["gameplay_log"]["scores"] == {"defender": 85.0, "attacker": 72.0}


# ------------------------------------------------------------------- CSV


def test_import_csv_log_with_bom(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = _upload(
        admin_client,
        match_id,
        content=SAMPLE_CSV.encode("utf-8"),
        filename="events.csv",
    )
    assert resp.status_code == 200, resp.text
    log = resp.json()["gameplay_log"]
    assert len(log["events"]) == 2
    assert log["events"][0] == {"time": "00:32", "type": "occupy", "text": "守护者占领了L2第1个格子 的SongName 任务名 (8) [守卫]"}
    # 掠夺者获胜 -> attacker；比分 72:85 -> defender=72, attacker=85。
    assert log["scores"] == {"defender": 72.0, "attacker": 85.0}
    assert log["winner"] == "attacker"


# ------------------------------------------------------- form-field override


def test_import_form_fields_override_parsed_values(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = _upload(
        admin_client,
        match_id,
        content=json.dumps(SAMPLE_EVENTS).encode("utf-8"),
        data={"score_a": "90", "score_b": "80", "winner": "attacker"},
    )
    assert resp.status_code == 200, resp.text
    log = resp.json()["gameplay_log"]
    assert log["scores"] == {"defender": 90.0, "attacker": 80.0}
    assert log["winner"] == "attacker"


def test_import_invalid_winner_form_field_400(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = _upload(
        admin_client,
        match_id,
        content=json.dumps(SAMPLE_EVENTS).encode("utf-8"),
        data={"winner": "red"},
    )
    assert resp.status_code == 400
    assert "winner" in resp.json()["detail"]


# ---------------------------------------------------------------- sync=true


def test_import_sync_true_prefills_match_result(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = _upload(
        admin_client,
        match_id,
        content=json.dumps(SAMPLE_EVENTS).encode("utf-8"),
        params={"sync": "true"},
    )
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        match = db.get(Match, match_id)
        assert match.gameplay_log is not None
        assert match.result["score_a"] == 85.0
        assert match.result["score_b"] == 72.0
        assert match.result["winner"] == match.participant_a  # defender -> participant_a
        assert match.result["is_draw"] is False
        assert match.result_type == "win"
        # 预填不结束对局：赛程推进仍由裁判 POST /result 完成。
        assert match.status == "in_progress"


def test_import_sync_draw_maps_winner_none(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    events = [
        {"time": "00:05", "text": "开局", "type": "system"},
        {"time": "12:30", "text": "游戏结束 — 时间到，平局（积分 50:50）", "type": "victory"},
    ]
    resp = _upload(admin_client, match_id, content=json.dumps(events).encode("utf-8"), params={"sync": "true"})
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        match = db.get(Match, match_id)
        assert match.result["winner"] is None
        assert match.result["is_draw"] is True
        assert match.result["score_a"] == 50.0
        assert match.result["score_b"] == 50.0
        assert match.result_type == "draw"
        assert match.status == "in_progress"


# ------------------------------------------------------------- idempotency


def test_reimport_overwrites_previous_log(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    first = _upload(admin_client, match_id, content=json.dumps(SAMPLE_EVENTS).encode("utf-8"))
    assert first.status_code == 200
    assert first.json()["gameplay_log"]["winner"] == "defender"

    other = [
        {"time": "00:10", "text": "A", "type": "occupy"},
        {"time": "12:30", "text": "游戏结束 — 时间到，掠夺者获胜（积分 30:99）", "type": "victory"},
    ]
    second = _upload(admin_client, match_id, content=json.dumps(other).encode("utf-8"))
    assert second.status_code == 200
    log = second.json()["gameplay_log"]
    assert len(log["events"]) == 2
    assert log["winner"] == "attacker"
    assert log["scores"] == {"defender": 30.0, "attacker": 99.0}

    # 无残留旧数据（stale_state 防护：覆盖而非累积）。
    assert log["events"][0]["text"] == "A"


# ------------------------------------------------------------- error clarity


def test_import_malformed_file_400(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = _upload(admin_client, match_id, content=b"not-json {[")
    assert resp.status_code == 400
    assert resp.json()["detail"]  # 非空、清晰的错误信息


def test_import_empty_file_400(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = _upload(admin_client, match_id, content=b"")
    assert resp.status_code == 400
    assert "空" in resp.json()["detail"]


def test_import_no_file_422(admin_client):
    match_id, referee_token = _seed(admin_client)
    _start(admin_client, match_id, referee_token)

    resp = admin_client.post(f"/api/matches/{match_id}/gameplay-log")
    assert resp.status_code == 422  # file 是必填 multipart 字段
