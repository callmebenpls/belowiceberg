import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth import SESSION_COOKIE

@pytest.fixture
def client(env, db):
    return TestClient(create_app())

def test_signup_creates_user_and_sets_cookie(client):
    r = client.post("/api/auth/signup", json={
        "email": "a@b.com", "password": "secret123", "display_name": "Ann"
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert SESSION_COOKIE in r.cookies

def test_signup_duplicate_email_409(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "B"})
    assert r.status_code == 409

def test_signup_rejects_short_password(client):
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "abc", "display_name": "A"})
    assert r.status_code == 400

def test_login_ok_sets_cookie(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/auth/login", json={"email": "a@b.com", "password": "secret123"})
    assert r.status_code == 200
    assert SESSION_COOKIE in r.cookies

def test_login_wrong_password_401(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong"})
    assert r.status_code == 401

def test_me_requires_session(client):
    assert client.get("/api/me").status_code == 401

def test_me_returns_profile(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "Ann"})
    r = client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "a@b.com"
    assert body["display_name"] == "Ann"
    assert body["is_admin"] is False
    assert body["cards_open_default"] is True

def test_logout_clears_cookie(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    assert client.get("/api/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401

def test_change_password_ok(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/me/change-password", json={"current": "secret123", "new": "newpw456"})
    assert r.status_code == 200
    # log out, log in with new
    client.post("/api/auth/logout")
    r2 = client.post("/api/auth/login", json={"email": "a@b.com", "password": "newpw456"})
    assert r2.status_code == 200

def test_change_password_wrong_current(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/me/change-password", json={"current": "WRONG", "new": "newpw456"})
    assert r.status_code == 401

def test_patch_me_updates_display_name(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "Old"})
    r = client.patch("/api/me", json={"display_name": "New"})
    assert r.status_code == 200
    assert client.get("/api/me").json()["display_name"] == "New"

def test_patch_me_updates_cards_open_default(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.patch("/api/me", json={"cards_open_default": False})
    assert r.status_code == 200
    assert client.get("/api/me").json()["cards_open_default"] is False

def test_clear_progress_endpoint(client, db):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    me = client.get("/api/me").json()
    db.execute("INSERT INTO reading_progress(user_id, book_slug, chapter, section) VALUES (?,?,?,?)",
               (me["id"], "gatsby", 1, 1))
    r = client.post("/api/me/clear-progress")
    assert r.status_code == 200
    rows = db.execute("SELECT 1 FROM reading_progress WHERE user_id = ?", (me["id"],)).fetchone()
    assert rows is None
