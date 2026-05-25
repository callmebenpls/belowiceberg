import re
from app.db import get_conn
from app import user_notes as un

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

class ProgressError(ValueError):
    pass

def _validate(slug: str, chapter: int, section: int) -> None:
    if not SLUG_RE.match(slug):
        raise ProgressError(f"invalid slug: {slug!r}")
    if not (1 <= int(chapter) <= 99):
        raise ProgressError(f"invalid chapter: {chapter}")
    if not (1 <= int(section) <= 999):
        raise ProgressError(f"invalid section: {section}")

def upsert_progress(user_id: int, book_slug: str, chapter: int, section: int) -> None:
    _validate(book_slug, chapter, section)
    get_conn().execute(
        "INSERT INTO reading_progress(user_id, book_slug, chapter, section) VALUES (?,?,?,?) "
        "ON CONFLICT(user_id, book_slug) DO UPDATE SET "
        "chapter=excluded.chapter, section=excluded.section, updated_at=datetime('now')",
        (user_id, book_slug, int(chapter), int(section)),
    )

def get_library_for(user_id: int) -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT book_slug, chapter, section, updated_at FROM reading_progress "
        "WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    books = [dict(r) for r in rows]
    current = books[0] if books else None
    notes = un.list_all_for_user(user_id)
    # Stats from updated_at — count distinct YYYY-MM-DD as sessions; compute current streak.
    days = conn.execute(
        "SELECT DISTINCT substr(updated_at, 1, 10) AS d FROM reading_progress "
        "WHERE user_id = ? ORDER BY d DESC",
        (user_id,),
    ).fetchall()
    day_set = {r["d"] for r in days}
    sessions = len(day_set)
    streak = _streak_days(day_set)
    return {
        "current": current,
        "books_in_progress": books,
        "all_my_notes": [
            {"id": n["id"], "book_slug": n["book_slug"], "paraId": n["para_id"],
             "category": n["category"], "selectedText": n["selected_text"],
             "responseMarkdown": n["response_markdown"], "createdAt": n["created_at"]}
            for n in notes
        ],
        "stats": {"sessions": sessions, "streak_days": streak},
    }

def _streak_days(day_set: set[str]) -> int:
    from datetime import date, timedelta
    today = date.today()
    streak = 0
    cur = today
    while cur.isoformat() in day_set:
        streak += 1
        cur -= timedelta(days=1)
    return streak
