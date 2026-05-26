import pytest
from fastapi.testclient import TestClient
from app.db import migrate, reset_conn
from app import books as bk
from app.users import create_user


@pytest.fixture
def client(env):
    reset_conn()
    migrate()
    yield


@pytest.fixture
def admin_client(client):
    create_user("admin@test.com", "testtest1", "Admin", is_admin=True)
    from app.main import create_app
    c = TestClient(create_app())
    r = c.post("/api/auth/login", json={"email": "admin@test.com", "password": "testtest1"})
    assert r.status_code == 200, r.text
    return c


def test_list_books_requires_admin(client):
    from app.main import create_app
    c = TestClient(create_app())
    r = c.get("/api/admin/books")
    assert r.status_code == 401


def test_list_books_empty(admin_client):
    r = admin_client.get("/api/admin/books")
    assert r.status_code == 200
    assert r.json() == []


def test_list_books_with_entry(admin_client):
    bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    r = admin_client.get("/api/admin/books")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["slug"] == "great-gatsby"
    assert data[0]["chapter_count"] == 0


def test_patch_book_status_published(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    r = admin_client.patch(f"/api/admin/books/{book_id}", json={"status": "published"})
    assert r.status_code == 200
    assert bk.get_book(book_id)["status"] == "published"


def test_patch_book_status_back_to_draft(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    admin_client.patch(f"/api/admin/books/{book_id}", json={"status": "published"})
    r = admin_client.patch(f"/api/admin/books/{book_id}", json={"status": "draft"})
    assert r.status_code == 200
    assert bk.get_book(book_id)["status"] == "draft"


def test_delete_book(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    r = admin_client.delete(f"/api/admin/books/{book_id}")
    assert r.status_code == 200
    with pytest.raises(bk.BookNotFoundError):
        bk.get_book(book_id)


def test_delete_nonexistent_book(admin_client):
    r = admin_client.delete("/api/admin/books/9999")
    assert r.status_code == 404


def test_get_chapters(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    bk.add_chapter(book_id, 1, "第一章", "Chapter text.")
    r = admin_client.get(f"/api/admin/books/{book_id}/chapters")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["chapter_num"] == 1


def test_get_paragraphs(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "text")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    bk.add_paragraph(sec_id, 1, "In my younger years.")
    r = admin_client.get(f"/api/admin/books/{book_id}/paragraphs")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_get_annotations(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "text")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    p_id = bk.add_paragraph(sec_id, 1, "In my younger years.")
    bk.upsert_annotation(p_id, "vocab", "younger", "Explanation.", "hash1")
    r = admin_client.get(f"/api/admin/books/{book_id}/annotations")
    assert r.status_code == 200
    assert len(r.json()) == 1
