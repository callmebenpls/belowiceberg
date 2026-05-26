import json
import pytest
from fastapi.testclient import TestClient
from app.db import migrate, reset_conn
from app import books as bk
from app.users import create_user


@pytest.fixture
def setup(env):
    reset_conn()
    migrate()
    create_user("admin@test.com", "testtest1", "Admin", is_admin=True)
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "Chapter text.")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    bk.add_paragraph(sec_id, 1, "In my younger years.")
    from app.main import create_app
    c = TestClient(create_app())
    r = c.post("/api/auth/login", json={"email": "admin@test.com", "password": "testtest1"})
    assert r.status_code == 200
    return c, book_id


def test_create_job(setup):
    c, book_id = setup
    r = c.post("/api/admin/jobs", json={
        "book_id": book_id,
        "scope_chapter_nums": [1],
        "dimensions": ["vocab"],
        "prompts": {"vocab": "Find vocab."},
        "depth": "standard",
        "language": "zh",
        "extra_instructions": None,
    })
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_get_job_status(setup):
    c, book_id = setup
    r = c.post("/api/admin/jobs", json={
        "book_id": book_id,
        "scope_chapter_nums": [1],
        "dimensions": ["vocab"],
        "prompts": {},
        "depth": "standard",
        "language": "zh",
        "extra_instructions": None,
    })
    job_id = r.json()["job_id"]
    r2 = c.get(f"/api/admin/jobs/{job_id}")
    assert r2.status_code == 200
    data = r2.json()
    assert data["id"] == job_id
    assert data["status"] in ("pending", "running", "done", "error")


def test_create_job_requires_admin(env):
    reset_conn()
    migrate()
    from app.main import create_app
    c = TestClient(create_app())
    r = c.post("/api/admin/jobs", json={
        "book_id": 1, "scope_chapter_nums": [1],
        "dimensions": ["vocab"], "prompts": {},
        "depth": "standard", "language": "zh", "extra_instructions": None,
    })
    assert r.status_code == 401


def test_get_nonexistent_job(setup):
    c, _ = setup
    r = c.get("/api/admin/jobs/9999")
    assert r.status_code == 404
