import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(env, db):
    return TestClient(create_app())

def _login(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})

def test_progress_requires_login(client):
    assert client.post("/api/progress", json={"book_slug": "gatsby", "chapter": 1, "section": 1}).status_code == 401
    assert client.get("/api/library").status_code == 401

def test_post_progress_then_library(client):
    _login(client)
    r = client.post("/api/progress", json={"book_slug": "gatsby", "chapter": 3, "section": 7})
    assert r.status_code == 200
    lib = client.get("/api/library").json()
    assert lib["current"]["book_slug"] == "gatsby"
    assert lib["current"]["chapter"] == 3
    assert lib["current"]["section"] == 7

def test_library_includes_notes(client):
    _login(client)
    client.post("/api/user-notes/gatsby", json={"paraId":"p","category":"vocab","selectedText":"x","responseMarkdown":"y"})
    lib = client.get("/api/library").json()
    assert len(lib["all_my_notes"]) == 1

def test_post_progress_bad_input(client):
    _login(client)
    r = client.post("/api/progress", json={"book_slug": "../etc", "chapter": 1, "section": 1})
    assert r.status_code == 400
    r2 = client.post("/api/progress", json={"book_slug": "gatsby", "chapter": 0, "section": 1})
    assert r2.status_code == 400
