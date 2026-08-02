import os
import tempfile

# Point DATABASE_URL at an isolated temp file BEFORE importing app modules,
# so tests never touch the real development database.
_tmp_db = os.path.join(tempfile.gettempdir(), "competition_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ["DB_PATH"] = _tmp_db

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture()
def admin_client(client):
    """A TestClient logged in as an admin (role flipped via a direct DB write).

    Registers a normal player through the API (auto-login sets the cookie),
    then flips that user's role to "admin" with a direct DB session. This is
    tests-only seeding — the app itself has no admin bootstrap (todo 24).
    """
    resp = client.post(
        "/api/auth/register",
        json={"username": "admin_user", "email": "admin@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "admin_user").one()
        user.role = "admin"
        db.commit()
    return client
