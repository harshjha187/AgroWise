"""
Shared pytest fixtures for the AgroWise backend test suite.

Key trick: server.py creates its Flask `app`, loads the API key, and calls
db.init_db() at IMPORT TIME. To avoid touching the real dev database or the
real .api_key file, we set AGROWISE_API_KEY and monkeypatch database.DB_PATH
to a temp file *before* importing server for the first time in the session.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_API_KEY = "test-suite-api-key-do-not-use-in-prod"


@pytest.fixture(scope="session")
def app_module(tmp_path_factory, monkeypatch_session):
    """Import server.py exactly once per test session, pointed at a throwaway
    SQLite file and a known API key instead of the real dev database/secret."""
    import os

    test_db = tmp_path_factory.mktemp("agrowise_test") / "test.db"
    os.environ["AGROWISE_API_KEY"] = TEST_API_KEY

    import database as db
    monkeypatch_session.setattr(db, "DB_PATH", test_db)

    import server  # noqa: F401  (import triggers db.init_db() against the patched path)
    return server


@pytest.fixture(scope="session")
def monkeypatch_session():
    """pytest's built-in monkeypatch fixture is function-scoped; this session-
    scoped variant lets the one-time app import patch DB_PATH permanently for
    the whole test run."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture
def client(app_module):
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


@pytest.fixture
def auth_headers():
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture(autouse=True)
def _clean_db(app_module):
    """Wipe all readings/alerts before every test via a direct DB call
    (bypassing the HTTP DELETE endpoint, which is itself rate-limited)."""
    import database as db
    db.clear_all()
    yield
    db.clear_all()
