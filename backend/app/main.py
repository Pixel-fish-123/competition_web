import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import the ORM models so Base.metadata knows about them for create_all.
import app.models.audit_log  # noqa: F401
import app.models.competition  # noqa: F401
import app.models.match  # noqa: F401
import app.models.point  # noqa: F401
import app.models.registration  # noqa: F401
import app.models.team  # noqa: F401
import app.models.user  # noqa: F401
from app.api.admin_traffic import router as admin_traffic_router
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.competitions import router as competitions_router
from app.api.health import router as health_router
from app.api.matches import router as matches_router
from app.api.points import router as points_router
from app.api.rankings import router as rankings_router
from app.api.registrations import router as registrations_router
from app.api.teams import router as teams_router
from app.api.ws import router as ws_router
from app.core.csrf import CSRFMiddleware
from app.core.ratelimit import limiter
from app.db import Base, engine
from app.plugins.registry import register_default_plugins
from app.plugins.routes import mount_gameplay_routes


def _ensure_schema_upgrades() -> None:
    """轻量 schema 升级（无 alembic）：给旧库 users 表补 nickname 列（幂等）。

    SQLite 的 ``create_all`` 不会为已存在的表补列；新库/测试库由
    create_all 建表时已含该列，PRAGMA 检测到后直接跳过。PRAGMA table_info
    返回行的 ``name`` 字段在下标 1。
    """
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
        if not rows or any(row[1] == "nickname" for row in rows):
            return
        conn.execute(text("ALTER TABLE users ADD COLUMN nickname VARCHAR(50)"))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB init strategy (documented): no alembic yet — create tables directly
    # on startup. app.models.user is imported above so the table is registered.
    Base.metadata.create_all(bind=engine)
    # 旧库 schema 升级（create_all 只建新表，不补已存在表的列）。
    _ensure_schema_upgrades()
    # 玩法插件（todo 12）：扫描注册 plugins/ 下的插件并自动挂载
    # /api/gameplay/<name>/* 路由（register_default_plugins 幂等）。
    register_default_plugins()
    mount_gameplay_routes(app)
    yield


app = FastAPI(title="萌新杯音游比赛网站", lifespan=lifespan)
app.state.limiter = limiter


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 统一 JSON 响应（限流超限）。"""
    return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Order note: the last add_middleware() call is the outermost middleware.
# CORS ends up outermost, CSRF inside it, SlowAPI innermost — CSRF still
# sees every request and rejects cross-site state-changing requests before
# they hit handlers, and rate limiting only counts requests that already
# passed CSRF (forged-origin POSTs are rejected without burning budget).
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(admin_traffic_router)
app.include_router(teams_router)
app.include_router(registrations_router)
app.include_router(competitions_router)
app.include_router(matches_router)
app.include_router(points_router)
app.include_router(rankings_router)
app.include_router(ws_router)

# Mount static files from frontend-dist if it exists at startup.
# The directory may not exist yet (frontend not built); do NOT create it.
_frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend-dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
