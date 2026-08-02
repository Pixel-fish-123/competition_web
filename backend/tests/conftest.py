import os
import tempfile

# Point DATABASE_URL at a temp file BEFORE importing app modules.
_tmp_db = os.path.join(tempfile.gettempdir(), "competition_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ["DB_PATH"] = _tmp_db
