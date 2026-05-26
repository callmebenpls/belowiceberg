from app.db import get_conn


class BookExistsError(ValueError):
    pass


class BookNotFoundError(LookupError):
    pass


def create_book(slug: str, title_en: str, title_zh: str, author: str,
                cover_css: str | None = None) -> int:
    conn = get_conn()
    if conn.execute("SELECT 1 FROM books WHERE slug=?", (slug,)).fetchone():
        raise BookExistsError(f"slug already exists: {slug}")
    cur = conn.execute(
        "INSERT INTO books(slug,title_en,title_zh,author,cover_css) VALUES(?,?,?,?,?)",
        (slug, title_en, title_zh, author, cover_css),
    )
    return cur.lastrowid


def get_book(book_id: int) -> dict:
    row = get_conn().execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not row:
        raise BookNotFoundError(book_id)
    return dict(row)


def list_books() -> list[dict]:
    rows = get_conn().execute("""
        SELECT b.*,
               COUNT(DISTINCT ch.id) AS chapter_count,
               COUNT(DISTINCT p.id)  AS total_paragraphs,
               COUNT(DISTINCT CASE WHEN a.id IS NOT NULL THEN p.id END) AS annotated_paragraphs
        FROM books b
        LEFT JOIN chapters ch ON ch.book_id = b.id
        LEFT JOIN sections sec ON sec.chapter_id = ch.id
        LEFT JOIN paragraphs p ON p.section_id = sec.id
        LEFT JOIN annotations a ON a.paragraph_id = p.id
        GROUP BY b.id
        ORDER BY b.created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


def update_book(book_id: int, status: str | None = None,
                cover_css: str | None = None) -> None:
    if status is not None and status not in ("draft", "published"):
        raise ValueError(f"invalid status: {status}")
    conn = get_conn()
    if status is not None:
        conn.execute("UPDATE books SET status=? WHERE id=?", (status, book_id))
    if cover_css is not None:
        conn.execute("UPDATE books SET cover_css=? WHERE id=?", (cover_css, book_id))


def delete_book(book_id: int) -> None:
    conn = get_conn()
    r = conn.execute("DELETE FROM books WHERE id=?", (book_id,))
    if r.rowcount == 0:
        raise BookNotFoundError(book_id)


def add_chapter(book_id: int, chapter_num: int, title_zh: str, text_full: str) -> int:
    cur = get_conn().execute(
        "INSERT INTO chapters(book_id,chapter_num,title_zh,text_full) VALUES(?,?,?,?)",
        (book_id, chapter_num, title_zh, text_full),
    )
    return cur.lastrowid


def add_section(chapter_id: int, section_num: int, title_zh: str | None = None) -> int:
    cur = get_conn().execute(
        "INSERT INTO sections(chapter_id,section_num,title_zh) VALUES(?,?,?)",
        (chapter_id, section_num, title_zh),
    )
    return cur.lastrowid


def add_paragraph(section_id: int, para_num: int, text_en: str) -> int:
    cur = get_conn().execute(
        "INSERT INTO paragraphs(section_id,para_num,text_en) VALUES(?,?,?)",
        (section_id, para_num, text_en),
    )
    return cur.lastrowid


def get_chapters_for_book(book_id: int) -> list[dict]:
    rows = get_conn().execute("""
        SELECT ch.*,
               COUNT(DISTINCT p.id) AS total_paragraphs,
               COUNT(DISTINCT CASE WHEN a.id IS NOT NULL THEN p.id END) AS annotated_paragraphs
        FROM chapters ch
        LEFT JOIN sections sec ON sec.chapter_id = ch.id
        LEFT JOIN paragraphs p ON p.section_id = sec.id
        LEFT JOIN annotations a ON a.paragraph_id = p.id
        WHERE ch.book_id = ?
        GROUP BY ch.id
        ORDER BY ch.chapter_num
    """, (book_id,)).fetchall()
    return [dict(r) for r in rows]


def get_paragraphs_for_book(book_id: int) -> list[dict]:
    rows = get_conn().execute("""
        SELECT p.id, p.section_id, p.para_num, p.text_en, p.worth_annotating,
               sec.section_num, sec.title_zh AS section_title,
               ch.chapter_num, ch.title_zh AS chapter_title, ch.id AS chapter_id
        FROM paragraphs p
        JOIN sections sec ON sec.id = p.section_id
        JOIN chapters ch ON ch.id = sec.chapter_id
        WHERE ch.book_id = ?
        ORDER BY ch.chapter_num, sec.section_num, p.para_num
    """, (book_id,)).fetchall()
    return [dict(r) for r in rows]


def get_annotations_for_book(book_id: int) -> list[dict]:
    rows = get_conn().execute("""
        SELECT a.*
        FROM annotations a
        JOIN paragraphs p ON p.id = a.paragraph_id
        JOIN sections sec ON sec.id = p.section_id
        JOIN chapters ch ON ch.id = sec.chapter_id
        WHERE ch.book_id = ?
        ORDER BY a.paragraph_id, a.dimension
    """, (book_id,)).fetchall()
    return [dict(r) for r in rows]


def upsert_annotation(paragraph_id: int, dimension: str, term: str,
                      body_markdown: str, prompt_version_hash: str,
                      model: str = "deepseek-chat") -> int:
    cur = get_conn().execute("""
        INSERT INTO annotations(paragraph_id,dimension,term,body_markdown,prompt_version_hash,model)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(paragraph_id,dimension,term)
        DO UPDATE SET body_markdown=excluded.body_markdown,
                      prompt_version_hash=excluded.prompt_version_hash,
                      model=excluded.model,
                      generated_at=datetime('now')
    """, (paragraph_id, dimension, term, body_markdown, prompt_version_hash, model))
    return cur.lastrowid


def set_worth_annotating(paragraph_ids: list[int], value: int) -> None:
    if not paragraph_ids:
        return
    placeholders = ",".join("?" * len(paragraph_ids))
    get_conn().execute(
        f"UPDATE paragraphs SET worth_annotating=? WHERE id IN ({placeholders})",
        [value] + paragraph_ids,
    )


def get_or_create_job(book_id: int, scope_json: str, dimensions_csv: str,
                      prompts_json: str, depth: str, language: str,
                      extra_instructions: str | None,
                      prompt_version_hash: str) -> int:
    cur = get_conn().execute("""
        INSERT INTO annotation_jobs(book_id,scope_json,dimensions_csv,prompts_json,
                                    depth,language,extra_instructions,prompt_version_hash)
        VALUES(?,?,?,?,?,?,?,?)
    """, (book_id, scope_json, dimensions_csv, prompts_json,
          depth, language, extra_instructions, prompt_version_hash))
    return cur.lastrowid


def get_job(job_id: int) -> dict:
    row = get_conn().execute("SELECT * FROM annotation_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise LookupError(f"job not found: {job_id}")
    return dict(row)


def update_job(job_id: int, **kwargs) -> None:
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    get_conn().execute(f"UPDATE annotation_jobs SET {sets} WHERE id=?", values)


def reset_stale_jobs() -> None:
    """Called on startup: reset any 'running' jobs to 'pending' for resumability."""
    get_conn().execute(
        "UPDATE annotation_jobs SET status='pending' WHERE status='running'"
    )
