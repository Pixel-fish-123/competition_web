"""Team endpoints: create / add member / remove member / disband / query.

Auth: todo 5 (app/core/rbac.py) has landed — ``get_current_user`` resolves the
authenticated user from the "token" cookie and rejects missing/banned accounts.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user
from app.db import get_db
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.team import MemberAddRequest, TeamCreate, TeamOut

router = APIRouter()

TEAM_MAX_MEMBERS = 3


def _get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="队伍不存在")
    return team


def _team_member_count(db: Session, team_id: int) -> int:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id).count()


def _user_in_team(db: Session, user_id: int) -> TeamMember | None:
    return db.query(TeamMember).filter(TeamMember.user_id == user_id).first()


def _team_out(db: Session, team: Team) -> dict:
    """Serialize a Team plus its member rows (ordered by join time).

    成员名称通过 TeamMember JOIN User 一次批量取出（避免 N+1）。
    """
    rows = (
        db.query(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .filter(TeamMember.team_id == team.id)
        .order_by(TeamMember.id)
        .all()
    )
    return {
        "id": team.id,
        "name": team.name,
        "captain_id": team.captain_id,
        "created_at": team.created_at,
        "member_count": len(rows),
        "members": [
            {
                "id": m.id,
                "user_id": m.user_id,
                "username": u.username,
                "nickname": u.nickname,
                "created_at": m.created_at,
            }
            for m, u in rows
        ],
    }


@router.post("/api/teams", response_model=TeamOut)
def create_team(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # The current user must not already be in any team (captain or member).
    if _user_in_team(db, user.id) is not None:
        raise HTTPException(status_code=400, detail="已加入队伍")

    team = Team(name=payload.name, captain_id=user.id)
    db.add(team)
    try:
        db.flush()  # materialize team.id; raises IntegrityError on dup name
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="队伍名称已存在")

    db.add(TeamMember(team_id=team.id, user_id=user.id))  # captain joins
    db.commit()
    db.refresh(team)
    return _team_out(db, team)


@router.post("/api/teams/{team_id}/members", response_model=TeamOut)
def add_member(
    team_id: int,
    payload: MemberAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team = _get_team_or_404(db, team_id)
    if team.captain_id != user.id:
        raise HTTPException(status_code=403, detail="只有队长可以添加成员")
    if _team_member_count(db, team_id) >= TEAM_MAX_MEMBERS:
        raise HTTPException(status_code=400, detail="队伍已满（最多3人）")

    # 两种定位方式：user_id 与 username 都提供时以 user_id 优先。
    if payload.user_id is not None:
        target_user_id = payload.user_id
        if db.get(User, payload.user_id) is None:
            raise HTTPException(status_code=404, detail="用户不存在")
    else:
        target = db.query(User).filter(User.username == payload.username).first()
        if target is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        target_user_id = target.id
    if _user_in_team(db, target_user_id) is not None:
        raise HTTPException(status_code=400, detail="该用户已在其他队伍")

    db.add(TeamMember(team_id=team.id, user_id=target_user_id))
    try:
        db.commit()
    except IntegrityError:
        # user_id unique race: user joined another team between check and commit.
        db.rollback()
        raise HTTPException(status_code=400, detail="该用户已在其他队伍")
    return _team_out(db, _get_team_or_404(db, team_id))


@router.delete("/api/teams/{team_id}/members/{user_id}")
def remove_member(
    team_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team = _get_team_or_404(db, team_id)
    if team.captain_id != user.id:
        raise HTTPException(status_code=403, detail="只有队长可以移除成员")
    if user_id == team.captain_id:
        raise HTTPException(status_code=400, detail="队长不能退出队伍，请解散或转让")

    member = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="该成员不在队伍中")
    db.delete(member)
    db.commit()
    return {"ok": True}


@router.delete("/api/teams/{team_id}")
def disband_team(
    team_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team = _get_team_or_404(db, team_id)
    if team.captain_id != user.id:
        raise HTTPException(status_code=403, detail="只有队长可以解散队伍")

    # Delete all member rows first, then the team itself.
    db.query(TeamMember).filter(TeamMember.team_id == team.id).delete()
    db.delete(team)
    db.commit()
    return {"ok": True}


# NOTE: /api/teams/my MUST be declared before /api/teams/{team_id} so "my"
# is not captured by the {team_id:int} path param.
@router.get("/api/teams/my")
def my_team(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    member = _user_in_team(db, user.id)
    if member is None:
        return {"team": None}
    team = _get_team_or_404(db, member.team_id)
    return {"team": _team_out(db, team)}


@router.get("/api/teams/{team_id}", response_model=TeamOut)
def get_team(
    team_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team = _get_team_or_404(db, team_id)
    return _team_out(db, team)
