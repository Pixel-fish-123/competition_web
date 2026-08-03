import os
import tempfile

# Point DATABASE_URL at an isolated temp file BEFORE importing app modules,
# so tests never touch the real development database. The file is unique per
# process (PID in the name): concurrent pytest runs (e.g. parallel workers on
# different todos) would otherwise drop/create each other's tables mid-flight.
_tmp_db = os.path.join(tempfile.gettempdir(), f"competition_test_{os.getpid()}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ["DB_PATH"] = _tmp_db

import pytest
from fastapi.testclient import TestClient

from app.core.lockout import reset_all as reset_lockout_all
from app.core.ratelimit import limiter
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.user import User


@pytest.fixture()
def client():
    # Fresh tables per test for full isolation. TestClient is entered as a
    # context manager so the app lifespan (create_all) also runs.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_traffic_state():
    """Clear module-level rate-limit + lockout state between tests.

    slowapi's Limiter and core/lockout.py both keep in-memory state shared
    across the whole test process; without a reset, counters would bleed
    between tests (e.g. login attempts in one test locking a username or
    exhausting the 10/minute budget for the next test).
    """
    limiter.reset()
    reset_lockout_all()
    yield


@pytest.fixture()
def admin_client(client):
    """A TestClient logged in as an admin (role flipped via a direct DB write).

    Uses its OWN TestClient instance so its cookie jar is independent: tests
    that register players through ``client`` (auto-login overwrites the
    player cookie) can still reach admin endpoints through ``admin_client``.
    Both clients share the same module-level engine / temp-DB file.
    """
    with TestClient(app) as admin:
        resp = admin.post(
            "/api/auth/register",
            json={"username": "admin_user", "email": "admin@example.com", "password": "secret123"},
        )
        assert resp.status_code == 200
        with SessionLocal() as db:
            user = db.query(User).filter(User.username == "admin_user").one()
            user.role = "admin"
            db.commit()
        yield admin
