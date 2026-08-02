import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import the ORM models so Base.metadata knows about them for create_all.
import app.models.competition  # noqa: F401
import app.models.match  # noqa: F401
import app.models.registration  # noqa: F401
import app.models.team  # noqa: F401
import app.models.user  # noqa: F401
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.competitions import router as competitions_router
from app.api.health import router as health_router
from app.api.matches import router as matches_router
from app.api.registrations import router as registrations_router
from app.api.teams import router as teams_router
from app.core.csrf import CSRFMiddleware
from app.db import Base, engine
from app.plugins.registry import register_default_plugins
from app.plugins.routes import mount_gameplay_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB init strategy (documented): no alembic yet — create tables directly
    # on startup. app.models.user is imported above so the table is registered.
    Base.metadata.create_all(bind=engine)
    # 玩法插件（todo 12）：扫描注册 plugins/ 下的插件并自动挂载
    # /api/gameplay/<name>/* 路由（register_default_plugins 幂等）。
    register_default_plugins()
    mount_gameplay_routes(app)
    yield


app = FastAPI(title="萌新杯音游比赛网站", lifespan=lifespan)

# Order note: the last add_middleware() call is the outermost middleware.
# CORS ends up outermost, CSRF inside it — CSRF still sees every request
# and rejects cross-site state-changing requests before they hit handlers.
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
app.include_router(teams_router)
app.include_router(registrations_router)
app.include_router(competitions_router)
app.include_router(matches_router)

# Mount static files from frontend-dist if it exists at startup.
# The directory may not exist yet (frontend not built); do NOT create it.
_frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend-dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
