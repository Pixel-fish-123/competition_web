"""Auth endpoints: register, login, logout, me.

Sessions are JWT-based, stored in an httpOnly SameSite=Lax cookie named "token".
Todo 16: account lockout (5 consecutive failures → 15 min, Metis C2) via
core/lockout.py, audit logging via core/audit.py, and slowapi rate limits
(10/minute per IP; the per-account dimension is the lockout module).
"""

import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.lockout import locked_until, record_failed_login, reset_lockout
from app.core.ratelimit import limiter
from app.core.rbac import get_current_user
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.config import settings
from app.db import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, RegisterRequest, UserMePatchRequest, UserOut

router = APIRouter()

COOKIE_NAME = "token"
COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days, seconds


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
