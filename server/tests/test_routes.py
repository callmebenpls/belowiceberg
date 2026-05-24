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

def _login(client):
    client.post("/admin/login", json={"password": "test"})

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
