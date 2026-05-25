import re
from app.db import get_conn

VALID_CATEGORIES = {"vocab", "grammar", "structure"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

class UserNoteError(ValueError):
    pass

def _validate(slug: str, para_id: str, category: str,
              selected_text: str, response_markdown: str) -> None:
    if not SLUG_RE.match(slug):
        raise UserNoteError(f"invalid slug: {slug!r}")
    if category not in VALID_CATEGORIES:
        raise UserNoteError(f"invalid category: {category!r}")
    if not para_id or not selected_text or not response_markdown:
        raise UserNoteError("para_id, selected_text, response_markdown required")
    if len(selected_text) > 2000 or len(response_markdown) > 8000:
        raise UserNoteError("field too long")

def append_note(user_id: int, book_slug: str, para_id: str,
                category: str, selected_text: str, response_markdown: str) -> int:
    _validate(book_slug, para_id, category, selected_text, response_markdown)
    cur = get_conn().execute(
        "INSERT INTO user_notes(user_id, book_slug, para_id, category, selected_text, response_markdown) "
        "VALUES (?,?,?,?,?,?)",
        (user_id, book_slug, para_id, category, selected_text, response_markdown),
    )
    return cur.lastrowid

def list_for_user_book(user_id: int, book_slug: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM user_notes WHERE user_id = ? AND book_slug = ? ORDER BY id",
        (user_id, book_slug),
    ).fetchall()
    return [dict(r) for r in rows]

def list_all_for_user(user_id: int) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM user_notes WHERE user_id = ? ORDER BY book_slug, id",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]
