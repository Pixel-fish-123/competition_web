"""Development seed script (todo 24): demo users / teams / competition.

Idempotent: if an ``admin`` user already exists, every run after the first
prints "已初始化，跳过" and does nothing — running the script twice never
duplicates rows. The dataset is dev-only and uses default passwords (printed
as a loud warning); never deploy with these credentials.

Usage (from backend/)::

    .venv\\Scripts\\python seed.py

Exposed as a function too::

    from seed import seed_all
    result = seed_all()  # uses SessionLocal; returns a summary dict
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models.competition import Competition
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User

ADMIN_USERNAME = "admin"
REFEREE_USERNAME = "referee"
PLAYER_USERNAMES = [f"player{i}" for i in range(1, 9)]
DEFAULT_PLAYER_PASSWORD = "player123"
ADMIN_PASSWORD = "admin123"
REFEREE_PASSWORD = "referee123"

COMPETITION_NAME = "萌新杯·演示赛"
COMPETITION_DESCRIPTION = "种子脚本创建的演示比赛：6 名玩家组成 2 队 + 2 名单人玩家。"

# seed.py lives in backend/; the demo song library sample sits at
# D:\myproject1\demo\test_songs.json (sibling of the repo root). Fallback to
# a demo/ dir inside the repo itself if the external sample is absent.
_DEFAULT_SONG_LIB_CANDIDATES = (
    Path(__file__).resolve().parent.parent.parent / "demo" / "test_songs.json",
    Path(__file__).resolve().parent / "demo" / "test_songs.json",
)

_DEV_PASSWORD_WARNING = """\
============================================================================
警告 / WARNING: 以下默认账号密码仅限本地开发环境使用!
  admin     / admin123
  referee   / referee123
  player1..8 / player123
生产/公网部署前请务必修改或删除这些种子账号，切勿保留默认口令。
============================================================================
"""


def _load_song_lib(song_lib: dict | None, song_lib_path: str | None) -> dict:
    """Resolve the song library dict: explicit dict > explicit path > env > demo file."""
    if song_lib is not None:
        return song_lib
    if song_lib_path is not None:
        return json.loads(Path(song_lib_path).read_text(encoding="utf-8"))
    env_path = os.environ.get("SONG_LIB_PATH")
    if env_path:
        return json.loads(Path(env_path).read_text(encoding="utf-8"))
    for candidate in _DEFAULT_SONG_LIB_CANDIDATES:
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        "找不到曲库文件 demo/test_songs.json；请通过 song_lib_path 或 "
        "SONG_LIB_PATH 指定"
    )


def seed_all(
    db=None,
    song_lib: dict | None = None,
    song_lib_path: str | None = None,
) -> dict[str, Any]:
    """Create the full demo dataset once; idempotent by admin username.

    - If an ``admin`` user already exists → print "已初始化，跳过", return
      ``{"skipped": True}`` and touch nothing (idempotency check FIRST).
    - Otherwise create 1 admin + 1 referee + 8 players, 2 teams of 3, 1 demo
      competition and 4 approved registrations inside a single transaction:
      any failure rolls back everything and re-raises.

    ``db`` may be injected (tests) or omitted (defaults to SessionLocal).
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        # Idempotency check FIRST — before any write.
        if db.query(User).filter(User.username == ADMIN_USERNAME).first() is not None:
            print("已初始化，跳过 (admin 已存在)")
            return {"skipped": True, "reason": "admin_exists"}

        try:
            admin = User(
                username=ADMIN_USERNAME,
                email="admin@dev.local",
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
                status="active",
            )
            db.add(admin)

            referee = User(
                username=REFEREE_USERNAME,
                email="referee@dev.local",
                password_hash=hash_password(REFEREE_PASSWORD),
                role="referee",
                status="active",
            )
            db.add(referee)

            players: dict[str, User] = {}
            for name in PLAYER_USERNAMES:
                player = User(
                    username=name,
                    email=f"{name}@dev.local",
                    password_hash=hash_password(DEFAULT_PLAYER_PASSWORD),
                    role="player",
                    status="active",
                )
                db.add(player)
                players[name] = player
            db.flush()  # ids for FK references below

            # Team A: player1 (captain) + player2 + player3.
            team_a = Team(name="萌新队A", captain_id=players["player1"].id)
            db.add(team_a)
            # Team B: player4 (captain) + player5 + player6.
            team_b = Team(name="萌新队B", captain_id=players["player4"].id)
            db.add(team_b)
            db.flush()

            def _add_members(team: Team, member_names: list[str]) -> None:
                for name in member_names:
                    db.add(
                        TeamMember(team_id=team.id, user_id=players[name].id)
                    )

            _add_members(team_a, ["player1", "player2", "player3"])
            _add_members(team_b, ["player4", "player5", "player6"])

            competition = Competition(
                name=COMPETITION_NAME,
                description=COMPETITION_DESCRIPTION,
                participant_type="mixed",
                tournament_format="round_robin",
                format_config={"group_size": 4},
                points_rule={"1": 100, "2": 60, "3": 40, "default": 10},
                gameplay_plugin="triangle_occupy",
                song_lib=_load_song_lib(song_lib, song_lib_path),
                referee_ids=[referee.id],
                max_participants=8,
                status="registration",
                created_by=admin.id,
            )
            db.add(competition)
            db.flush()

            # 4 approved participant units: 2 teams + 2 individual players.
            registrations = [
                Registration(
                    competition_id=competition.id,
                    participant_type="team",
                    team_id=team_a.id,
                    user_id=team_a.captain_id,
                    status="approved",
                    approved_by=admin.id,
                ),
                Registration(
                    competition_id=competition.id,
                    participant_type="team",
                    team_id=team_b.id,
                    user_id=team_b.captain_id,
                    status="approved",
                    approved_by=admin.id,
                ),
                Registration(
                    competition_id=competition.id,
                    participant_type="individual",
                    user_id=players["player7"].id,
                    status="approved",
                    approved_by=admin.id,
                ),
                Registration(
                    competition_id=competition.id,
                    participant_type="individual",
                    user_id=players["player8"].id,
                    status="approved",
                    approved_by=admin.id,
                ),
            ]
            db.add_all(registrations)

            db.commit()
        except Exception:
            db.rollback()
            raise

        summary = {
            "skipped": False,
            "users": 10,
            "teams": 2,
            "team_members": 6,
            "competitions": 1,
            "registrations": 4,
        }
        print(
            "种子数据已创建:\n"
            f"  用户      : 1 admin + 1 referee + 8 players = {summary['users']}\n"
            f"  队伍      : 萌新队A / 萌新队B，各 3 人 = {summary['teams']} 队 / "
            f"{summary['team_members']} 名成员\n"
            f"  比赛      : {COMPETITION_NAME} (round_robin + triangle_occupy)\n"
            f"  报名      : 队A / 队B / player7 / player8 = {summary['registrations']} 条 (已通过)"
        )
        return summary
    finally:
        if owns_session:
            db.close()


def main() -> int:
    """CLI entry: create tables if missing, warn about dev passwords, seed."""
    print(_DEV_PASSWORD_WARNING)
    Base.metadata.create_all(bind=engine)
    seed_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
