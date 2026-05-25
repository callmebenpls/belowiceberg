import pytest
from app.progress import upsert_progress, get_library_for, ProgressError

def _mk_user(db, email="a@b.com"):
    from app.users import create_user
    return create_user(email, "secret123", "A")

def test_upsert_creates_then_updates(db):
    uid = _mk_user(db)
    upsert_progress(uid, "gatsby", 1, 5)
    upsert_progress(uid, "gatsby", 2, 1)
    rows = db.execute("SELECT chapter, section FROM reading_progress WHERE user_id = ?", (uid,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["chapter"] == 2
    assert rows[0]["section"] == 1

def test_upsert_different_books_separate_rows(db):
    uid = _mk_user(db)
    upsert_progress(uid, "gatsby", 1, 5)
    upsert_progress(uid, "henry",  2, 3)
    rows = db.execute("SELECT book_slug FROM reading_progress WHERE user_id = ?", (uid,)).fetchall()
    assert {r["book_slug"] for r in rows} == {"gatsby", "henry"}

def test_get_library_for_empty(db):
    uid = _mk_user(db)
    lib = get_library_for(uid)
    assert lib["current"] is None
    assert lib["books_in_progress"] == []
    assert lib["all_my_notes"] == []
    assert lib["stats"]["sessions"] == 0
    assert lib["stats"]["streak_days"] == 0

def test_get_library_picks_most_recent_as_current(db):
    uid = _mk_user(db)
    upsert_progress(uid, "gatsby", 1, 1)
    import time; time.sleep(1.1)
    upsert_progress(uid, "henry", 2, 2)
    lib = get_library_for(uid)
    assert lib["current"]["book_slug"] == "henry"
    assert {b["book_slug"] for b in lib["books_in_progress"]} == {"gatsby", "henry"}

def test_get_library_includes_notes(db):
    from app.user_notes import append_note
    uid = _mk_user(db)
    append_note(uid, "gatsby", "p1", "vocab", "x", "y")
    lib = get_library_for(uid)
    assert len(lib["all_my_notes"]) == 1

def test_upsert_rejects_bad_slug(db):
    uid = _mk_user(db)
    with pytest.raises(ProgressError):
        upsert_progress(uid, "../etc", 1, 1)

def test_upsert_rejects_bad_numbers(db):
    uid = _mk_user(db)
    with pytest.raises(ProgressError):
        upsert_progress(uid, "gatsby", 0, 1)
    with pytest.raises(ProgressError):
        upsert_progress(uid, "gatsby", 1, 0)
