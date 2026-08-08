"""Auth endpoints: register, login, logout, me.

Sessions are JWT-based, stored in an httpOnly SameSite=Lax cookie named "token".
Todo 16: account lockout (5 consecutive failures → 15 min, Metis C2) via
core/lockout.py, audit logging via core/audit.py, and slowapi rate limits
(10/minute per IP; the per-account dimension is the lockout module).
"""

import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core.audit import log_audit
from app.core.ip_ban import ban_ip
from app.core.lockout import locked_until, record_failed_login, reset_lockout
from app.core.ratelimit import limiter
from app.core.rbac import get_current_user
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.user import LoginRequest, RegisterRequest, UserMePatchRequest, UserOut

router = APIRouter()

COOKIE_NAME = "token"
COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days, seconds

# 恶意登录自动拉黑：24h 内失败登录达到阈值即把该 IP 加入黑名单（全站封禁）。
IP_AUTO_BAN_THRESHOLD = 20
IP_AUTO_BAN_WINDOW_HOURS = 24
LOOPBACK_IPS = ("127.0.0.1", "::1", "localhost")


def _set_auth_cookie(response: Response, user_id: int, role: str) -> None:
    token = create_access_token(user_id, role)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.AUTH_COOKIE_SECURE,
    )


def _request_meta(request: Request) -> tuple[str, str | None]:
    """(ip, user_agent) 供审计日志使用。"""
    ip = request.client.host if request.client else "unknown"
    return ip, request.headers.get("user-agent")


def _auto_ban_ip(db: Session, ip: str) -> None:
    """24h 内失败登录 ≥20 次的 IP 自动拉黑（本地回环豁免）。

    统计基于审计表（持久化，重启不丢失）；core/ip_ban.ban_ip 幂等。
    """
    if not ip or ip in LOOPBACK_IPS:
        return
    recent = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "login_failed",
            AuditLog.ip == ip,
            AuditLog.created_at
            >= datetime.now(timezone.utc) - timedelta(hours=IP_AUTO_BAN_WINDOW_HOURS),
        )
        .count()
    )
    if recent >= IP_AUTO_BAN_THRESHOLD:
        ban_ip(db, ip, "自动拉黑：24小时内失败登录次数过多", None)


@router.post("/api/auth/register", response_model=UserOut)
@limiter.limit("10/minute")
def register(request: Request, payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first() is not None:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=payload.username,
        email=payload.email,
        nickname=payload.nickname,
        password_hash=hash_password(payload.password),
        role="player",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    ip, user_agent = _request_meta(request)
    log_audit(db, user.id, "register", ip, user_agent, {"username": user.username})
    _set_auth_cookie(response, user.id, user.role)
    return user  # auto-login on register


@router.post("/api/auth/login", response_model=UserOut)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    ip, user_agent = _request_meta(request)

    # Lockout check FIRST: even a correct password is rejected while locked (423).
    until = locked_until(payload.username)
    if until is not None:
        remaining = max(1, int(until - time.time()))
        raise HTTPException(status_code=423, detail=f"账号已锁定，请{remaining}秒后再试")

    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        record_failed_login(payload.username, ip)
        log_audit(db, None, "login_failed", ip, user_agent, {"username": payload.username})
        _auto_ban_ip(db, ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    reset_lockout(payload.username)
    log_audit(db, user.id, "login", ip, user_agent, {"username": user.username})
    _set_auth_cookie(response, user.id, user.role)
    return user


@router.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/api/auth/me", response_model=UserOut)
def me(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


@router.patch("/api/auth/me", response_model=UserOut)
def update_me(
    payload: UserMePatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """普通用户修改自己的资料（当前仅昵称；None=不修改）。"""
    if payload.nickname is not None:
        user.nickname = payload.nickname
        db.commit()
        db.refresh(user)
    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        user.id,
        "update_profile",
        ip,
        user_agent,
        {"username": user.username, "nickname": user.nickname},
    )
    return user
