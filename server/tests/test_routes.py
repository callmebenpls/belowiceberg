import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth import SESSION_COOKIE

@pytest.fixture
def client(env, db):
    return TestClient(create_app())

def _signup(client, email="admin@b.com", admin_via_db=False):
    """Sign up via the new auth route. If admin_via_db, flip is_admin in DB."""
    client.post("/api/auth/signup", json={"email": email, "password": "secret123", "display_name": "T"})
    if admin_via_db:
        from app.db import get_conn
        conn = get_conn()
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
        conn.commit()

def _login(client):
    _signup(client, admin_via_db=True)

def test_get_notes_is_public(client):
    r = client.get("/api/notes/gatsby")
    assert r.status_code == 200
    assert r.json() == []

def test_get_notes_empty(client):
    _login(client)
    r = client.get("/api/notes/gatsby")
    assert r.status_code == 200
    assert r.json() == []

def test_post_and_get_roundtrip(client):
    _login(client)
    note = {
        "paraId": "para3",
        "category": "vocab",
        "selectedText": "advantages",
        "responseMarkdown": "**advantages** — 优势",
    }
    r = client.post("/api/notes/gatsby", json=note)
    assert r.status_code == 201
    r2 = client.get("/api/notes/gatsby")
    assert r2.status_code == 200
    body = r2.json()
    assert len(body) == 1
    assert body[0]["selectedText"] == "advantages"
    assert body[0]["createdAt"]

def test_post_rejects_bad_category(client):
    _login(client)
    bad = {"paraId": "p", "category": "bogus",
           "selectedText": "x", "responseMarkdown": "y"}
    r = client.post("/api/notes/gatsby", json=bad)
    assert r.status_code == 400

def test_post_rejects_bad_slug(client):
    _login(client)
    note = {"paraId": "p", "category": "vocab",
            "selectedText": "x", "responseMarkdown": "y"}
    r = client.post("/api/notes/..%2Fetc%2Fpasswd", json=note)
    assert r.status_code in (400, 404)

def test_query_requires_auth(client):
    r = client.post("/api/query", json={
        "category": "vocab", "selectedText": "x", "paraContext": "y"
    })
    assert r.status_code == 401

def test_query_streams(client, httpx_mock):
    _login(client)
    httpx_mock.add_response(
        url="https://api.deepseek.com/chat/completions",
        method="POST",
        text=(
            'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            'data: [DONE]\n\n'
        ),
        headers={"Content-Type": "text/event-stream"},
    )
    with client.stream("POST", "/api/query", json={
        "category": "vocab",
        "selectedText": "advice",
        "paraContext": "He gave me some advice.",
    }) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode()
    assert "data: hi" in body
    assert "data: [DONE]" in body

def test_query_bad_category(client):
    _login(client)
    r = client.post("/api/query", json={
        "category": "bogus", "selectedText": "x", "paraContext": "y"
    })
    assert r.status_code == 422  # pydantic validation
