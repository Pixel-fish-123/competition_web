"""Auth endpoints: register, login, logout, me.

Sessions are JWT-based, stored in an httpOnly SameSite=Lax cookie named "token".
TODO 16 will build account-lockout on top of FAILED_LOGINS.
"""

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, RegisterRequest, UserOut

router = APIRouter()

# In-memory failed-login counters for later lockout logic (todo 16).
FAILED_LOGINS = {"by_username": {}, "by_ip": {}}

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
        secure=False,  # dev; flip to True behind HTTPS in production
    )


def _record_failed_login(username: str, ip: str) -> None:
    FAILED_LOGINS["by_username"][username] = FAILED_LOGINS["by_username"].get(username, 0) + 1
    FAILED_LOGINS["by_ip"][ip] = FAILED_LOGINS["by_ip"].get(ip, 0) + 1


@router.post("/api/auth/register", response_model=UserOut)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first() is not None:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="player",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _set_auth_cookie(response, user.id, user.role)
    return user  # auto-login on register


@router.post("/api/auth/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        _record_failed_login(payload.username, request.client.host if request.client else "unknown")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

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
