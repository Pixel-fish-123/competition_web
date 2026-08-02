import os
import tempfile

# Point DATABASE_URL at an isolated temp file BEFORE importing app modules,
# so tests never touch the real development database.
_tmp_db = os.path.join(tempfile.gettempdir(), "competition_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ["DB_PATH"] = _tmp_db

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    # Fresh tables per test for full isolation. TestClient is entered as a
    # context manager so the app lifespan (create_all) also runs.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
