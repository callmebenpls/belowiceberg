import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(env, db):
    return TestClient(create_app())

def _login(client, email="a@b.com"):
    client.post("/api/auth/signup", json={"email": email, "password": "secret123", "display_name": "A"})

def test_user_notes_requires_login(client):
    assert client.get("/api/user-notes/gatsby").status_code == 401
    assert client.post("/api/user-notes/gatsby", json={}).status_code == 401

def test_post_then_get_returns_only_my_notes(client):
    _login(client, "a@b.com")
    note = {"paraId": "p1", "category": "vocab",
            "selectedText": "x", "responseMarkdown": "y"}
    r = client.post("/api/user-notes/gatsby", json=note)
    assert r.status_code == 201
    r2 = client.get("/api/user-notes/gatsby")
    assert r2.status_code == 200
    body = r2.json()
    assert len(body) == 1
    assert body[0]["selectedText"] == "x"
    assert "createdAt" in body[0]

def test_other_user_does_not_see_my_notes(client):
    _login(client, "a@b.com")
    client.post("/api/user-notes/gatsby", json={"paraId": "p","category":"vocab","selectedText":"x","responseMarkdown":"y"})
    client.post("/api/auth/logout")
    _login(client, "b@b.com")
    assert client.get("/api/user-notes/gatsby").json() == []

def test_post_bad_category(client):
    _login(client)
    r = client.post("/api/user-notes/gatsby",
                    json={"paraId":"p","category":"bogus","selectedText":"x","responseMarkdown":"y"})
    assert r.status_code == 422  # pydantic Literal rejection

def test_post_bad_slug(client):
    _login(client)
    r = client.post("/api/user-notes/..etc",
                    json={"paraId":"p","category":"vocab","selectedText":"x","responseMarkdown":"y"})
    assert r.status_code == 400
