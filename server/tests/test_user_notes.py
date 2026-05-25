import pytest
from app.user_notes import append_note, list_for_user_book, list_all_for_user, UserNoteError

def _mk_user(db, email="a@b.com"):
    from app.users import create_user
    return create_user(email, "secret123", "A")

def test_append_and_list_for_book(db):
    uid = _mk_user(db)
    append_note(uid, "gatsby", "para1", "vocab", "advantages", "**adv** 优势")
    notes = list_for_user_book(uid, "gatsby")
    assert len(notes) == 1
    assert notes[0]["selected_text"] == "advantages"
    assert notes[0]["response_markdown"].startswith("**adv**")

def test_list_for_book_returns_only_user_and_book(db):
    u1 = _mk_user(db, "a@b.com")
    u2 = _mk_user(db, "c@d.com")
    append_note(u1, "gatsby", "p", "vocab", "x", "y")
    append_note(u1, "henry",  "p", "vocab", "x", "y")
    append_note(u2, "gatsby", "p", "vocab", "x", "y")
    g1 = list_for_user_book(u1, "gatsby")
    assert len(g1) == 1
    assert all(n["book_slug"] == "gatsby" for n in g1)

def test_list_all_for_user(db):
    u1 = _mk_user(db)
    append_note(u1, "gatsby", "p1", "vocab", "x", "y")
    append_note(u1, "henry",  "p1", "grammar", "x", "y")
    all_notes = list_all_for_user(u1)
    assert len(all_notes) == 2
    assert {n["book_slug"] for n in all_notes} == {"gatsby", "henry"}

def test_append_rejects_bad_category(db):
    uid = _mk_user(db)
    with pytest.raises(UserNoteError):
        append_note(uid, "gatsby", "p", "bogus", "x", "y")

def test_append_rejects_bad_slug(db):
    uid = _mk_user(db)
    with pytest.raises(UserNoteError):
        append_note(uid, "../etc", "p", "vocab", "x", "y")

def test_append_rejects_empty_fields(db):
    uid = _mk_user(db)
    with pytest.raises(UserNoteError):
        append_note(uid, "gatsby", "", "vocab", "x", "y")
