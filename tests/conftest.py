"""Shared pytest fixtures for VNGG_LMS.

Mỗi test dùng 1 file DB SQLite riêng (tmp_path) — monkeypatch app.shared.DB_PATH,
init_lms_db() để dựng schema, seed 4 user + 1 program cơ bản.
"""
import os
import sys

# Repo root vào sys.path để `from app.shared import ...` chạy được từ tests/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from app import shared
from app.main import app as flask_app
from modules.lms.routes import init_lms_db


@pytest.fixture
def app(monkeypatch, tmp_path):
    db_file = tmp_path / "test_lms.db"
    monkeypatch.setattr(shared, "DB_PATH", str(db_file))
    init_lms_db()
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret-do-not-use-in-prod")
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed(app):
    """Insert baseline: 1 admin (id=1), 2 instructors (id=2,3), 1 learner (id=4), 1 program (id=1)."""
    conn = shared.get_db()
    conn.executescript("""
        INSERT INTO lms_users (id,email,name,role) VALUES
          (1,'admin@x.com','Boss','admin'),
          (2,'t1@x.com','T1','instructor'),
          (3,'t2@x.com','T2','instructor'),
          (4,'alice@x.com','Alice','learner');
        INSERT INTO lms_programs (id,name) VALUES (1,'NextGen 2026');
    """)
    conn.commit(); conn.close()


@pytest.fixture
def login(client):
    """Bypass /lms/login POST — inject session vars directly."""
    def _login(user_id, role, name="Test User"):
        with client.session_transaction() as sess:
            sess["lms_user_id"] = user_id
            sess["lms_user_role"] = role
            sess["lms_user_name"] = name
    return _login
