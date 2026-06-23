import pytest
import os
import tempfile
from werkzeug.security import generate_password_hash
from finance_app import create_app
from finance_app.db import get_db, init_db, execute_db

@pytest.fixture
def app():
    # Create a temporary file to isolate the database for each test run
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app("testing")
    app.config["DATABASE_PATH"] = db_path
    
    with app.app_context():
        init_db()
        # Seed default administrative and member test users
        hashed_pwd = generate_password_hash("testpass")
        execute_db(
            "INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
            ("Test Admin", "admin", hashed_pwd, "admin", "2026-01-01 00:00:00")
        )
        execute_db(
            "INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
            ("Test Member", "member", hashed_pwd, "member", "2026-01-01 00:00:00")
        )
        execute_db("INSERT INTO fund (id, total_balance) VALUES (1, 20000)")
        get_db().commit()
        
    yield app
    
    # Teardown database file
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except OSError:
        pass

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

class AuthActions(object):
    def __init__(self, client):
        self._client = client

    def login(self, username="member", password="testpass"):
        # We need a GET first to acquire a session / cookie context or we submit data
        # Note: CSRF protection is disabled in TestingConfig, so we don't need csrf_token here!
        return self._client.post(
            "/login",
            data={"username": username, "password": password}
        )

    def logout(self):
        return self._client.get("/logout")

@pytest.fixture
def auth(client):
    return AuthActions(client)
