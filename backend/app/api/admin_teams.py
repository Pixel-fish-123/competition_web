"""Admin-only 团队管理端点（后台拉人组建团队）。

- GET    /api/admin/teams            全部队伍（含成员/队长/是否有报名）
- POST   /api/admin/teams            建队（队长 + 成员名单 ≤3 人）
- PATCH  /api/admin/teams/{id}       改名 / 改队长 / 改成员
- DELETE /api/admin/teams/{id}       删除无报名记录的队伍

约束（用户确认）：
- 有报名记录的队伍：仅允许改名；改成员/队长返回 400（避免进行中比赛的
  赛程/成绩错乱）。改队长时同步更新该队报名行的 user_id（报名行存队长）。
- 删除：有报名记录的队伍拒绝删除。
- 用户全局唯一属于一支队伍（team_members.user_id unique）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.ratelimit import limiter
from app.core.rbac import require_admin
from app.db import get_db
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.team import AdminTeamCreate, AdminTeamUpdate

router = APIRouter(dependencies=[Depends(require_admin)])

TEAM_MAX_MEMBERS = 3


def _request_meta(request: Request) -> tuple[str, str | None]:
    ip = request.client.host if request.client else "unknown"
    return ip, request.headers.get("user-agent")


def _team_out(db: Session, team: Team) -> dict:
    """序列化队伍：成员（按加入顺序）+ 队长名称 + 是否有报名记录。"""
    rows = (
        db.query(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .filter(TeamMember.team_id == team.id)
        .order_by(TeamMember.id)
        .all()
    )
    captain = db.get(User, team.captain_id)
    has_regs = (
        db.query(Registration).filter(Registration.team_id == team.id).count() > 0
    )
    return {
        "id": team.id,
        "name": team.name,
        "captain_id": team.captain_id,
        "captain_username": captain.username if captain else None,
        "captain_nickname": captain.nickname if captain else None,
        "created_at": team.created_at,
        "member_count": len(rows),
        "has_registrations": has_regs,
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


def _team_name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = db.query(Team).filter(Team.name == name)
    if exclude_id is not None:
        query = query.filter(Team.id != exclude_id)
    return query.first() is not None


def _validate_users(db: Session, user_ids: list[int], exclude_team_id: int | None = None) -> None:
    """校验用户存在且未被其他队伍占用（排除当前队伍的现有成员）。"""
    if len(user_ids) > TEAM_MAX_MEMBERS:
        raise HTTPException(status_code=400, detail=f"队伍最多 {TEAM_MAX_MEMBERS} 人")
    for user_id in user_ids:
        if db.get(User, user_id) is None:
            raise HTTPException(status_code=404, detail=f"用户 {user_id} 不存在")
    occupied = (
        db.query(TeamMember.user_id)
        .filter(TeamMember.user_id.in_(user_ids))
        .all()
    )
    occupied_ids = {row[0] for row in occupied}
    if exclude_team_id is not None:
        current = {
            row[0]
            for row in (
                db.query(TeamMember.user_id)
                .filter(TeamMember.team_id == exclude_team_id)
                .all()
            )
        }
        occupied_ids -= current
    if occupied_ids:
        raise HTTPException(status_code=400, detail="部分用户已在其他队伍，无法加入")


@router.get("/api/admin/teams")
@limiter.limit("60/minute")
def list_teams(request: Request, db: Session = Depends(get_db)):
    """全部队伍（按创建顺序），含成员与队长名称。"""
    teams = db.query(Team).order_by(Team.id).all()
    return [_team_out(db, team) for team in teams]


@router.post("/api/admin/teams")
@limiter.limit("60/minute")
def create_team(
    payload: AdminTeamCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """后台建队：队长 + 成员名单（≤3 人，队长必在成员内）。"""
    if _team_name_taken(db, payload.name):
        raise HTTPException(status_code=400, detail="队伍名称已存在")
    _validate_users(db, payload.member_ids)

    team = Team(name=payload.name, captain_id=payload.captain_id)
    db.add(team)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="队伍名称已存在")
    for user_id in payload.member_ids:
        db.add(TeamMember(team_id=team.id, user_id=user_id))
    db.commit()
    db.refresh(team)

    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        admin.id,
        "admin_team_create",
        ip,
        user_agent,
        {"team_id": team.id, "team_name": team.name, "captain_id": payload.captain_id},
    )
    return _team_out(db, team)


@router.patch("/api/admin/teams/{team_id}")
@limiter.limit("60/minute")
def update_team(
    team_id: int,
    payload: AdminTeamUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """改名 / 改队长 / 改成员。有报名记录的队伍仅允许改名。"""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="队伍不存在")

    has_regs = (
        db.query(Registration).filter(Registration.team_id == team.id).count() > 0
    )

    changed: list[str] = []
    if payload.name is not None:
        if _team_name_taken(db, payload.name, exclude_id=team.id):
            raise HTTPException(status_code=400, detail="队伍名称已存在")
        team.name = payload.name
        changed.append("name")

    if payload.captain_id is not None or payload.member_ids is not None:
        if has_regs:
            raise HTTPException(
                status_code=400, detail="该队伍已有报名记录，只能修改队伍名称"
            )

        new_member_ids = payload.member_ids
        new_captain_id = payload.captain_id
        current_members = {
            row[0]
            for row in db.query(TeamMember.user_id)
            .filter(TeamMember.team_id == team.id)
            .all()
        }
        if new_member_ids is None:
            new_member_ids = sorted(current_members)
        if new_captain_id is None:
            new_captain_id = payload.captain_id or team.captain_id
        if new_captain_id not in new_member_ids:
            raise HTTPException(status_code=400, detail="队长必须包含在成员名单中")

        _validate_users(db, new_member_ids, exclude_team_id=team.id)

        # 成员差集：删除被移除的、新增进入的。
        to_remove = current_members - set(new_member_ids)
        if to_remove:
            db.query(TeamMember).filter(
                TeamMember.team_id == team.id,
                TeamMember.user_id.in_(to_remove),
            ).delete(synchronize_session=False)
        for user_id in new_member_ids:
            if user_id not in current_members:
                db.add(TeamMember(team_id=team.id, user_id=user_id))

        if new_captain_id != team.captain_id:
            team.captain_id = new_captain_id
            changed.append("captain")

        if payload.member_ids is not None:
            changed.append("members")

    db.commit()
    db.refresh(team)

    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        admin.id,
        "admin_team_update",
        ip,
        user_agent,
        {"team_id": team.id, "fields": changed},
    )
    return _team_out(db, team)


@router.delete("/api/admin/teams/{team_id}")
@limiter.limit("60/minute")
def delete_team(
    team_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """删除无报名记录的队伍（有报名则拒绝，避免破坏赛程/成绩）。"""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="队伍不存在")
    has_regs = (
        db.query(Registration).filter(Registration.team_id == team.id).count() > 0
    )
    if has_regs:
        raise HTTPException(status_code=400, detail="该队伍已有报名记录，无法删除")

    db.query(TeamMember).filter(TeamMember.team_id == team.id).delete(
        synchronize_session=False
    )
    db.delete(team)
    db.commit()

    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        admin.id,
        "admin_team_delete",
        ip,
        user_agent,
        {"team_id": team_id, "team_name": team.name},
    )
    return {"ok": True}
