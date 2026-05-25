import pytest
from app.users import (
    create_user, verify_credentials, get_by_id, get_by_email,
    update_display_name, update_cards_open_default,
    change_password, clear_progress, delete_user,
    UserExistsError, UserNotFoundError, WrongPasswordError,
)

def test_create_user_returns_id_and_normalizes_email(db):
    uid = create_user("Foo@Example.com", "secret123", "Foo")
    assert isinstance(uid, int)
    u = get_by_id(uid)
    assert u["email"] == "foo@example.com"
    assert u["display_name"] == "Foo"
    assert u["is_admin"] == 0
    assert u["cards_open_default"] == 1

def test_create_duplicate_email_raises(db):
    create_user("a@b.com", "secret123", "A")
    with pytest.raises(UserExistsError):
        create_user("A@B.com", "other", "Other")

def test_verify_credentials_ok(db):
    uid = create_user("a@b.com", "secret123", "A")
    assert verify_credentials("a@b.com", "secret123") == uid

def test_verify_credentials_wrong_password(db):
    create_user("a@b.com", "secret123", "A")
    assert verify_credentials("a@b.com", "nope") is None

def test_verify_credentials_unknown_email(db):
    assert verify_credentials("ghost@b.com", "x") is None

def test_get_by_email_returns_none_if_missing(db):
    assert get_by_email("ghost@b.com") is None

def test_update_display_name(db):
    uid = create_user("a@b.com", "secret123", "Old")
    update_display_name(uid, "New")
    assert get_by_id(uid)["display_name"] == "New"

def test_update_cards_open_default(db):
    uid = create_user("a@b.com", "secret123", "A")
    update_cards_open_default(uid, False)
    assert get_by_id(uid)["cards_open_default"] == 0

def test_change_password_ok(db):
    uid = create_user("a@b.com", "secret123", "A")
    change_password(uid, "secret123", "newpw456")
    assert verify_credentials("a@b.com", "newpw456") == uid
    assert verify_credentials("a@b.com", "secret123") is None

def test_change_password_wrong_current(db):
    uid = create_user("a@b.com", "secret123", "A")
    with pytest.raises(WrongPasswordError):
        change_password(uid, "wrong", "newpw456")

def test_clear_progress_only_affects_one_user(db):
    u1 = create_user("a@b.com", "secret123", "A")
    u2 = create_user("c@d.com", "secret123", "C")
    db.execute("INSERT INTO reading_progress(user_id, book_slug, chapter, section) VALUES (?,?,?,?)",
               (u1, "gatsby", 1, 1))
    db.execute("INSERT INTO reading_progress(user_id, book_slug, chapter, section) VALUES (?,?,?,?)",
               (u2, "gatsby", 2, 2))
    clear_progress(u1)
    rows = db.execute("SELECT user_id FROM reading_progress").fetchall()
    assert [r["user_id"] for r in rows] == [u2]

def test_delete_user_cascades_notes_and_progress(db):
    uid = create_user("a@b.com", "secret123", "A")
    db.execute("INSERT INTO user_notes(user_id,book_slug,para_id,category,selected_text,response_markdown) VALUES (?,?,?,?,?,?)",
               (uid, "gatsby", "para1", "vocab", "x", "y"))
    db.execute("INSERT INTO reading_progress(user_id, book_slug, chapter, section) VALUES (?,?,?,?)",
               (uid, "gatsby", 1, 1))
    delete_user(uid)
    assert db.execute("SELECT 1 FROM user_notes").fetchone() is None
    assert db.execute("SELECT 1 FROM reading_progress").fetchone() is None
    with pytest.raises(UserNotFoundError):
        get_by_id(uid)
