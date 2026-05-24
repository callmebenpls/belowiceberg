import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth import SESSION_COOKIE

@pytest.fixture
def client(env):
    return TestClient(create_app())

def test_login_wrong_password(client):
    r = client.post("/admin/login", json={"password": "wrong"})
    assert r.status_code == 401

def test_login_correct_sets_cookie(client):
    r = client.post("/admin/login", json={"password": "test"})
    assert r.status_code == 200
    assert SESSION_COOKIE in r.cookies

def test_admin_status_requires_session(client):
    assert client.get("/admin").status_code == 401

def test_admin_status_with_session(client):
    client.post("/admin/login", json={"password": "test"})
    r = client.get("/admin")
    assert r.status_code == 200
    assert r.json() == {"role": "admin"}

def test_logout_clears_cookie(client):
    client.post("/admin/login", json={"password": "test"})
    r = client.post("/admin/logout")
    assert r.status_code == 200
    # subsequent admin call should fail
    assert client.get("/admin").status_code == 401
