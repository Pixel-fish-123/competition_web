import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


def _ensure_schema_upgrades() -> None:
    """轻量 schema 升级（无 alembic）：给旧库补列（幂等）。

    SQLite 的 ``create_all`` 不会为已存在的表补列；新库/测试库由
    create_all 建表时已含该列，PRAGMA 检测到后直接跳过。PRAGMA table_info
    返回行的 ``name`` 字段在下标 1。目前升级项：
    - ``users.nickname``（历史遗留）
    - ``matches.gameplay_log``（玩法日志导入字段）
    """
    with engine.connect() as conn:
        users = conn.execute(text("PRAGMA table_info(users)")).fetchall()
        if users and not any(row[1] == "nickname" for row in users):
            conn.execute(text("ALTER TABLE users ADD COLUMN nickname VARCHAR(50)"))
        matches = conn.execute(text("PRAGMA table_info(matches)")).fetchall()
        if matches and not any(row[1] == "gameplay_log" for row in matches):
            conn.execute(text("ALTER TABLE matches ADD COLUMN gameplay_log JSON"))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB init strategy (documented): no alembic yet — create tables directly
    # on startup. app.models.user is imported above so the table is registered.
    Base.metadata.create_all(bind=engine)
    # 旧库 schema 升级（create_all 只建新表，不补已存在表的列）。
    _ensure_schema_upgrades()
    # 玩法插件已从对局流程中解耦（对局由裁判手工管理，不再挂载玩法路由）。
    # 插件目录保留作参考/未来使用，但不再 register + mount。
    # 摘除上一轮 lifespan 追加的 API 兜底（幂等重入），保证兜底始终排在全部
    # 真实 API 路由之后 —— 兜底匹配 /api/* 全路径，会遮蔽其后注册的任何路由。
    _drop_tail_routes(app)
    # 未匹配 /api/* 的 JSON 404 兜底（避免落入前端托管得到 index.html/405）。
    app.include_router(_api_fallback_router)
    # 前端静态托管：FastAPI 0.141 原生 frontend（低优先级路由 —— 全部普通
    # 路由之后才匹配，天然规避 Mount("/") 遮蔽晚注册玩法路由的问题），
    # fallback="index.html" 支持 SPA history 深链（/login、/competitions/1）
    # 与 http.ts 401 硬跳转。幂等：只注册一次（测试反复进入 lifespan）。
    if os.path.isdir(_frontend_dist) and getattr(app.router, "_frontend_routes", None) is None:
        app.frontend("/", directory=_frontend_dist, fallback="index.html")
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

# 静态托管目录：frontend/dist（todo 4 与 Vite 默认构建产物对齐）。
# 托管本身不用 Mount("/")：lifespan 阶段才 include 的 API 兜底路由
# 会排在 Mount 之后被遮蔽（FastAPI 0.141 _IncludedRouter 按注册顺序匹配）。
# 改用原生 app.frontend()（低优先级路由，全部普通路由之后匹配），在 lifespan
# 内注册（见 lifespan），既无遮蔽问题，也支持 SPA 深链回退 index.html。
_frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist")

# 未匹配的 /api/* 请求统一返回 JSON 404：前端托管会把未匹配 GET 回退成
# index.html、非 GET 回成 405，掩盖"接口不存在"。该兜底路由在 lifespan 内、
# 真实 API 路由与玩法路由之后 include（见 lifespan）。
_api_fallback_router = APIRouter()


@_api_fallback_router.api_route(
    "/api/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
)
def _api_fallback(full_path: str) -> JSONResponse:
    """未知 API 路径 -> 404（而不是落入前端托管，得到 index.html/405）。"""
    return JSONResponse(status_code=404, content={"detail": "接口不存在"})


def _drop_tail_routes(app: FastAPI) -> None:
    """移除上一轮 lifespan 追加的 API 兜底（幂等重入清理）。

    /api/* 兜底路由会遮蔽其后注册的任何路由（FastAPI 0.141 的 _IncludedRouter
    按注册顺序匹配）。每次进入 lifespan 都先把兜底从路由表摘除，待真实 API
    路由挂载完再追加到末尾，保证顺序始终是 [API 路由, API 兜底]。
    """
    app.router.routes[:] = [
        r
        for r in app.router.routes
        if getattr(r, "original_router", None) is not _api_fallback_router
    ]
