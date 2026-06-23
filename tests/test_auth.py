import pytest
from flask import session

def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Welcome Back" in response.data

def test_login_invalid_credentials(client):
    response = client.post("/login", data={"username": "wrong", "password": "wrong"})
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data

def test_login_member_success(client, auth):
    response = auth.login("member", "testpass")
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"

def test_login_admin_success(client, auth):
    response = auth.login("admin", "testpass")
    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/dashboard"

def test_logout(client, auth):
    auth.login("member", "testpass")
    response = auth.logout()
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

@pytest.mark.parametrize("path", (
    "/dashboard",
    "/chat",
    "/request_loan",
    "/submit_payment_proof",
    "/loan_tracking"
))
def test_login_required_redirects(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

@pytest.mark.parametrize("path", (
    "/admin/dashboard",
    "/admin/loans",
    "/contribution_tracking",
    "/admin/payment_proofs",
    "/admin/manage_payments"
))
def test_admin_required_redirects_non_admin(client, auth, path):
    auth.login("member", "testpass")
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"
