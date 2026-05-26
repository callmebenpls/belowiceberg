import pytest
from app.db import migrate, get_conn, reset_conn
from app import books as bk


@pytest.fixture
def db(env):
    reset_conn()
    migrate()
    yield get_conn()
    reset_conn()


def test_create_and_get_book(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    assert book_id > 0
    b = bk.get_book(book_id)
    assert b["slug"] == "great-gatsby"
    assert b["status"] == "draft"


def test_slug_unique(db):
    bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    with pytest.raises(bk.BookExistsError):
        bk.create_book("great-gatsby", "Dup", "重复", "Author")


def test_list_books_empty(db):
    assert bk.list_books() == []


def test_list_books_with_progress(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "Chapter one text.")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    bk.add_paragraph(sec_id, 1, "In my younger years.")
    books = bk.list_books()
    assert len(books) == 1
    assert books[0]["chapter_count"] == 1
    assert books[0]["total_paragraphs"] == 1
    assert books[0]["annotated_paragraphs"] == 0


def test_update_status(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    bk.update_book(book_id, status="published")
    b = bk.get_book(book_id)
    assert b["status"] == "published"


def test_update_status_invalid(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    with pytest.raises(ValueError):
        bk.update_book(book_id, status="annotating")


def test_get_paragraphs_for_book(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "text")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    p_id = bk.add_paragraph(sec_id, 1, "Hello world.")
    rows = bk.get_paragraphs_for_book(book_id)
    assert len(rows) == 1
    assert rows[0]["id"] == p_id
    assert rows[0]["text_en"] == "Hello world."


def test_get_annotations_for_book(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "text")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    p_id = bk.add_paragraph(sec_id, 1, "Hello world.")
    bk.upsert_annotation(p_id, "vocab", "Hello", "Greeting.", "abc123")
    anns = bk.get_annotations_for_book(book_id)
    assert len(anns) == 1
    assert anns[0]["term"] == "Hello"


def test_upsert_annotation_idempotent(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "text")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    p_id = bk.add_paragraph(sec_id, 1, "Hello.")
    bk.upsert_annotation(p_id, "vocab", "Hello", "First body.", "hash1")
    bk.upsert_annotation(p_id, "vocab", "Hello", "Updated body.", "hash2")
    anns = bk.get_annotations_for_book(book_id)
    assert len(anns) == 1
    assert anns[0]["body_markdown"] == "Updated body."


def test_delete_book(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    bk.delete_book(book_id)
    with pytest.raises(bk.BookNotFoundError):
        bk.get_book(book_id)


def test_reset_stale_jobs(db):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    job_id = bk.get_or_create_job(book_id, "[]", "vocab", "{}", "standard", "zh", None, "hash")
    bk.update_job(job_id, status="running")
    bk.reset_stale_jobs()
    job = bk.get_job(job_id)
    assert job["status"] == "pending"
