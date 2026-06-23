import pytest
import sqlite3
from finance_app.db import get_db, query_db, execute_db

def test_tables_created(app):
    with app.app_context():
        # Verify essential tables exist
        tables = query_db("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [t["name"] for t in tables]
        assert "members" in table_names
        assert "loans" in table_names
        assert "fund" in table_names
        assert "interest_payments" in table_names
        assert "monthly_contributions" in table_names
        assert "payment_proofs" in table_names
        assert "messages" in table_names

def test_role_check_constraint(app):
    with app.app_context():
        db = get_db()
        # Invalid role 'super_user' should trigger check constraint failure
        with pytest.raises(sqlite3.IntegrityError):
            execute_db(
                "INSERT INTO members (name, username, password, role) VALUES (?, ?, ?, ?)",
                ("Test User", "testuser", "pass", "super_user")
            )
            db.commit()

def test_foreign_key_constraint(app):
    with app.app_context():
        db = get_db()
        # Insertion of loan for non-existent member should trigger foreign key failure
        with pytest.raises(sqlite3.IntegrityError):
            execute_db(
                "INSERT INTO loans (member_id, amount, total_months) VALUES (?, ?, ?)",
                (999, 5000, 12)
            )
            db.commit()
