"""TDD tests for the dev seed script (todo 24): dataset shape + idempotency.

Isolated from the API-tests' ``client`` fixture: each test recreates the
tables on the shared per-PID temp DB, then calls ``seed.seed_all`` directly
with an injected session (``song_lib`` passed in-memory / via tmp file so the
tests never depend on the external demo song library).
"""

import json

import pytest

from app.core.security import verify_password
from app.db import Base, SessionLocal, engine
from app.models.competition import Competition
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User
from seed import seed_all

SONG_LIB = {"songs": [{"name": "Test Song", "type": "Hard", "level": "1"}]}


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        yield session


def _counts(session):
    return {
        "users": session.query(User).count(),
        "admins": session.query(User).filter(User.role == "admin").count(),
        "referees": session.query(User).filter(User.role == "referee").count(),
        "players": session.query(User).filter(User.role == "player").count(),
        "teams": session.query(Team).count(),
        "team_members": session.query(TeamMember).count(),
        "competitions": session.query(Competition).count(),
        "registrations": session.query(Registration).count(),
    }


def test_seed_creates_full_demo_dataset(db, tmp_path):
    song_file = tmp_path / "songs.json"
    song_file.write_text(json.dumps(SONG_LIB), encoding="utf-8")

    result = seed_all(db, song_lib_path=str(song_file))

    assert result["skipped"] is False
    assert result["users"] == 10

    counts = _counts(db)
    assert counts["users"] == 10
    assert counts["admins"] == 1
    assert counts["referees"] == 1
    assert counts["players"] == 8
    assert counts["teams"] == 2
    assert counts["team_members"] == 6
    assert counts["competitions"] == 1
    assert counts["registrations"] == 4

    # Every team has exactly 3 members, captain is its first member.
    for team in db.query(Team).order_by(Team.id).all():
        members = (
            db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
        )
        assert len(members) == 3
        assert team.captain_id in [m.user_id for m in members]

    # Team captains are player1 (A) and player4 (B).
    team_a, team_b = db.query(Team).order_by(Team.id).all()
    player1 = db.query(User).filter(User.username == "player1").one()
    player4 = db.query(User).filter(User.username == "player4").one()
    assert team_a.captain_id == player1.id
    assert team_b.captain_id == player4.id

    # The single demo competition has the exact planned shape.
    comp = db.query(Competition).one()
    assert comp.name == "萌新杯·演示赛"
    assert comp.participant_type == "mixed"
    assert comp.tournament_format == "round_robin"
    assert comp.format_config == {"group_size": 4}
    assert comp.points_rule == {"1": 100, "2": 60, "3": 40, "default": 10}
    assert comp.gameplay_plugin == "triangle_occupy"
    assert comp.status == "registration"
    assert comp.max_participants == 8
    assert comp.song_lib == SONG_LIB  # loaded from the tmp file
    referee = db.query(User).filter(User.role == "referee").one()
    assert comp.referee_ids == [referee.id]
    admin = db.query(User).filter(User.role == "admin").one()
    assert comp.created_by == admin.id

    # 4 approved registrations: 2 team (A/B) + 2 individual (player7/8).
    regs = db.query(Registration).order_by(Registration.id).all()
    assert len(regs) == 4
    assert all(r.status == "approved" for r in regs)
    assert [r.participant_type for r in regs].count("team") == 2
    assert [r.participant_type for r in regs].count("individual") == 2

    # Seeded passwords are verifiable (hash_password roundtrip).
    assert verify_password("admin123", admin.password_hash)
    assert verify_password("referee123", referee.password_hash)
    assert verify_password("player123", player1.password_hash)


def test_seed_twice_is_idempotent(db):
    first = seed_all(db, song_lib=SONG_LIB)
    before = _counts(db)

    second = seed_all(db, song_lib=SONG_LIB)

    assert first["skipped"] is False
    assert second["skipped"] is True
    assert _counts(db) == before  # nothing duplicated


def test_seeded_admin_can_login(client):
    """End-to-end: seeded admin credentials work against the real auth API."""
    with SessionLocal() as session:
        seed_all(session, song_lib=SONG_LIB)

    resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "admin"
    assert resp.json()["role"] == "admin"
