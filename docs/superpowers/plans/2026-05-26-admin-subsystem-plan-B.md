# BelowIceberg Admin Subsystem — Implementation Plan B

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the admin dashboard, annotation editor, and DeepSeek-powered annotation runner so an admin can upload books and generate annotation cards.

**Architecture:** FastAPI backend with new SQLite tables (books/chapters/sections/paragraphs/annotations/annotation_jobs), static HTML admin pages served from the web root, and a background asyncio worker that calls DeepSeek V3 and streams results to the editor via SSE.

**Tech Stack:** Python 3.11, FastAPI, SQLite, httpx, ebooklib, BeautifulSoup4, vanilla JS, SSE

---

## File Map

**New server files:**
- `server/migrations/002_books.sql` — 6 new tables
- `server/app/books.py` — book/chapter/section/paragraph CRUD and queries
- `server/app/annotation_runner.py` — background worker, DeepSeek calls, job lifecycle
- `server/app/routes/admin_books.py` — `/api/admin/books/*` routes
- `server/app/routes/admin_jobs.py` — `/api/admin/jobs/*` routes + SSE
- `server/app/epub_parser.py` — EPUB → DB rows via ebooklib
- `server/scripts/seed_gatsby.py` — one-time seed of Gatsby from HTML
- `server/tests/test_books.py`
- `server/tests/test_annotation_runner.py`
- `server/tests/test_routes_admin_books.py`
- `server/tests/test_routes_admin_jobs.py`

**Modified server files:**
- `server/app/main.py` — add 2 new routers
- `server/app/deepseek.py` — add `call_once()` non-streaming function
- `server/pyproject.toml` — add ebooklib, beautifulsoup4

**New frontend files:**
- `admin/index.html` — admin dashboard
- `admin/styles.css` — dashboard styles
- `admin/edit/index.html` — annotation editor
- `admin/edit/styles.css` — editor styles

**Modified deploy files:**
- `deploy/nginx-belowiceberg.conf` — replace `/admin` proxy block with static file serving

---

### Task 1: DB migration — 6 new tables

**Files:**
- Create: `server/migrations/002_books.sql`

- [ ] **Step 1: Write the migration**

```sql
-- server/migrations/002_books.sql

CREATE TABLE IF NOT EXISTS books (
    id          INTEGER PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    title_en    TEXT NOT NULL,
    title_zh    TEXT NOT NULL,
    author      TEXT NOT NULL,
    cover_css   TEXT,
    status      TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','published')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_num INTEGER NOT NULL,
    title_zh    TEXT NOT NULL,
    text_full   TEXT NOT NULL,
    UNIQUE(book_id, chapter_num)
);

CREATE TABLE IF NOT EXISTS sections (
    id          INTEGER PRIMARY KEY,
    chapter_id  INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    section_num INTEGER NOT NULL,
    title_zh    TEXT,
    UNIQUE(chapter_id, section_num)
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id               INTEGER PRIMARY KEY,
    section_id       INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    para_num         INTEGER NOT NULL,
    text_en          TEXT NOT NULL,
    worth_annotating INTEGER NOT NULL DEFAULT 1,
    UNIQUE(section_id, para_num)
);

CREATE TABLE IF NOT EXISTS annotations (
    id                  INTEGER PRIMARY KEY,
    paragraph_id        INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    dimension           TEXT NOT NULL
        CHECK(dimension IN ('vocab','grammar','syntax','lit','cult','style','overview')),
    term                TEXT NOT NULL,
    body_markdown       TEXT NOT NULL,
    prompt_version_hash TEXT NOT NULL,
    model               TEXT NOT NULL DEFAULT 'deepseek-chat',
    generated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(paragraph_id, dimension, term)
);

CREATE TABLE IF NOT EXISTS annotation_jobs (
    id               INTEGER PRIMARY KEY,
    book_id          INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    scope_json       TEXT NOT NULL,
    dimensions_csv   TEXT NOT NULL,
    prompts_json     TEXT NOT NULL,
    depth            TEXT NOT NULL DEFAULT 'standard'
        CHECK(depth IN ('light','standard','deep')),
    language         TEXT NOT NULL DEFAULT 'zh'
        CHECK(language IN ('zh','en','bilingual')),
    extra_instructions TEXT,
    prompt_version_hash TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','error')),
    progress_done    INTEGER NOT NULL DEFAULT 0,
    progress_total   INTEGER NOT NULL DEFAULT 0,
    error_message    TEXT,
    started_at       TEXT,
    completed_at     TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO schema_version (version) VALUES (2);
```

- [ ] **Step 2: Verify migration runs clean**

```bash
cd server
source .venv/bin/activate
BELOWICEBERG_DATA_DIR=/tmp/test-migrate \
  ADMIN_PASSWORD_HASH='$2b$12$YJTEgo/E1vhvLDoU.YZejeUU3DDmm6kQuH1/Ko7kg34a/RlgMX1oa' \
  SESSION_SECRET=test DEEPSEEK_API_KEY=sk-test \
  python -c "from app.db import migrate; migrate(); print('OK')"
```

Expected: `OK` (no errors)

- [ ] **Step 3: Verify schema_version = 2**

```bash
BELOWICEBERG_DATA_DIR=/tmp/test-migrate \
  ADMIN_PASSWORD_HASH='$2b$12$YJTEgo/E1vhvLDoU.YZejeUU3DDmm6kQuH1/Ko7kg34a/RlgMX1oa' \
  SESSION_SECRET=test DEEPSEEK_API_KEY=sk-test \
  python -c "
from app.db import migrate, get_conn
migrate()
row = get_conn().execute('SELECT version FROM schema_version').fetchone()
assert row[0] == 2, f'expected 2, got {row[0]}'
print('schema_version =', row[0])
"
```

Expected: `schema_version = 2`

- [ ] **Step 4: Commit**

```bash
git add server/migrations/002_books.sql
git commit -m "feat: add books/chapters/sections/paragraphs/annotations/annotation_jobs tables"
```

---

### Task 2: books.py — book and content CRUD

**Files:**
- Create: `server/app/books.py`
- Create: `server/tests/test_books.py`

- [ ] **Step 1: Write failing tests**

```python
# server/tests/test_books.py
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
```

- [ ] **Step 2: Run tests — verify they all fail**

```bash
cd server && pytest tests/test_books.py -v 2>&1 | head -20
```

Expected: all fail with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write books.py**

```python
# server/app/books.py
from app.db import get_conn

class BookExistsError(ValueError): pass
class BookNotFoundError(LookupError): pass

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
    conn = get_conn()
    cur = conn.execute("""
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
```

- [ ] **Step 4: Run tests — all pass**

```bash
cd server && pytest tests/test_books.py -v
```

Expected: 9/9 PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/books.py server/tests/test_books.py
git commit -m "feat: add books.py module with book/chapter/section/paragraph CRUD"
```

---

### Task 3: deepseek.py — add call_once() for non-streaming JSON

**Files:**
- Modify: `server/app/deepseek.py`
- Modify: `server/tests/test_deepseek.py`

- [ ] **Step 1: Add test for call_once**

Open `server/tests/test_deepseek.py` and append:

```python
# append to existing test_deepseek.py
import pytest
import httpx
from pytest_httpx import HTTPXMock

@pytest.mark.asyncio
async def test_call_once_returns_content(env, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.deepseek.com/chat/completions",
        json={
            "choices": [{"message": {"content": '{"vocab":[]}'}}]
        }
    )
    from app.deepseek import call_once
    result = await call_once("sys prompt", "user msg")
    assert result == '{"vocab":[]}'

@pytest.mark.asyncio
async def test_call_once_raises_on_error(env, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.deepseek.com/chat/completions",
        status_code=429,
        text="rate limited",
    )
    from app.deepseek import call_once, DeepSeekError
    with pytest.raises(DeepSeekError, match="429"):
        await call_once("sys", "user")
```

- [ ] **Step 2: Run — verify new tests fail**

```bash
cd server && pytest tests/test_deepseek.py::test_call_once_returns_content -v
```

Expected: FAIL with `ImportError: cannot import name 'call_once'`

- [ ] **Step 3: Add call_once to deepseek.py**

Append to the bottom of `server/app/deepseek.py`:

```python
async def call_once(system: str, user: str, temperature: float = 0.3) -> str:
    """Single non-streaming call. Returns full response text."""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {load_config().deepseek_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(DEEPSEEK_URL, json=body, headers=headers)
        if r.status_code >= 400:
            raise DeepSeekError(f"DeepSeek {r.status_code}: {r.text[:200]!r}")
        data = r.json()
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run all deepseek tests**

```bash
cd server && pytest tests/test_deepseek.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/deepseek.py server/tests/test_deepseek.py
git commit -m "feat: add call_once() to deepseek module for non-streaming JSON calls"
```

---

### Task 4: annotation_runner.py — background worker

**Files:**
- Create: `server/app/annotation_runner.py`
- Create: `server/tests/test_annotation_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# server/tests/test_annotation_runner.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch
from app.db import migrate, get_conn, reset_conn
from app import books as bk

@pytest.fixture
def db(env):
    reset_conn()
    migrate()
    # seed a minimal book
    book_id = bk.create_book("test-book", "Test Book", "测试书", "Author")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "Chapter one full text.")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    bk.add_paragraph(sec_id, 1, "In my younger years.")
    bk.add_paragraph(sec_id, 2, "He.")  # trivial
    yield get_conn(), book_id
    reset_conn()

def _make_job(book_id: int) -> int:
    return bk.get_or_create_job(
        book_id=book_id,
        scope_json=json.dumps([1]),  # chapter_num 1
        dimensions_csv="vocab,grammar",
        prompts_json=json.dumps({"vocab": "Find vocabulary.", "grammar": "Find grammar."}),
        depth="standard",
        language="zh",
        extra_instructions=None,
        prompt_version_hash="abc123",
    )

@pytest.mark.asyncio
async def test_run_job_produces_annotations(db, monkeypatch):
    conn, book_id = db
    job_id = _make_job(book_id)
    queue = asyncio.Queue()

    pre_pass_response = json.dumps([1])  # only para 1 worth annotating
    ann_response = json.dumps({
        "vocab": [{"term": "younger", "body_markdown": "Explanation of younger."}],
        "grammar": []
    })

    call_count = 0
    async def fake_call_once(system, user, temperature=0.3):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return pre_pass_response  # pre-pass filter
        return ann_response  # paragraph annotation

    monkeypatch.setattr("app.annotation_runner.call_once", fake_call_once)

    from app.annotation_runner import run_job
    await run_job(job_id, queue)

    events = []
    while not queue.empty():
        events.append(await queue.get())

    types = [e["type"] for e in events]
    assert "annotation" in types
    assert types[-1] == "done"

    # Check annotation was persisted
    anns = bk.get_annotations_for_book(book_id)
    assert len(anns) == 1
    assert anns[0]["term"] == "younger"
    assert anns[0]["dimension"] == "vocab"

@pytest.mark.asyncio
async def test_run_job_idempotent(db, monkeypatch):
    conn, book_id = db
    # Pre-seed an annotation with same hash
    paras = bk.get_paragraphs_for_book(book_id)
    p_id = paras[0]["id"]
    bk.upsert_annotation(p_id, "vocab", "younger", "Old body.", "abc123")

    job_id = _make_job(book_id)
    queue = asyncio.Queue()

    call_count = 0
    async def fake_call_once(system, user, temperature=0.3):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps([p_id])
        return json.dumps({"vocab": [{"term": "younger", "body_markdown": "New body."}]})

    monkeypatch.setattr("app.annotation_runner.call_once", fake_call_once)
    from app.annotation_runner import run_job
    await run_job(job_id, queue)

    anns = bk.get_annotations_for_book(book_id)
    assert len(anns) == 1
    # Same hash: body should be updated (upsert always updates)
    assert anns[0]["body_markdown"] == "New body."

@pytest.mark.asyncio
async def test_run_job_error_handling(db, monkeypatch):
    conn, book_id = db
    job_id = _make_job(book_id)
    queue = asyncio.Queue()

    from app.deepseek import DeepSeekError
    async def fake_call_once(system, user, temperature=0.3):
        raise DeepSeekError("rate limit")

    monkeypatch.setattr("app.annotation_runner.call_once", fake_call_once)
    from app.annotation_runner import run_job
    await run_job(job_id, queue)

    events = []
    while not queue.empty():
        events.append(await queue.get())

    assert events[-1]["type"] == "error"
    job = bk.get_job(job_id)
    assert job["status"] == "error"
    assert "rate limit" in job["error_message"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd server && pytest tests/test_annotation_runner.py -v 2>&1 | head -15
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write annotation_runner.py**

```python
# server/app/annotation_runner.py
import asyncio
import json
import hashlib
from app.deepseek import call_once, DeepSeekError
from app import books as bk

_job_lock = asyncio.Lock()

DIMENSION_LABELS = {
    "vocab": "词汇", "grammar": "语法", "syntax": "句法",
    "lit": "文学手法", "cult": "文化背景", "style": "风格分析",
}

DEFAULT_PROMPTS = {
    "vocab": "Identify vocabulary worth teaching: unusual words, literary diction, words used in unexpected ways. For each, write a 2-3 sentence explanation in the target language.",
    "grammar": "Identify grammatical structures worth teaching: tenses, passive voice, complex clauses. Explain the structure and why it matters here.",
    "syntax": "Identify syntactic patterns worth teaching: sentence length, inversion, parallelism, fragmentation. Explain the effect.",
    "lit": "Identify literary devices: metaphor, simile, irony, foreshadowing, allusion. Explain the device and its effect.",
    "cult": "Identify cultural references: historical events, geography, social customs, period details. Explain what a non-Western reader needs to know.",
    "style": "Identify stylistic choices: register, tone, rhythm, word choice. Explain what they reveal about the narrator or characters.",
}


def compute_prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode()).hexdigest()[:16]


def build_system_prompt(dimensions: list[str], prompts: dict[str, str],
                        depth: str, language: str,
                        extra: str | None) -> str:
    depth_desc = {"light": "brief (1-2 items max per dimension)",
                  "standard": "thorough (2-4 items per dimension)",
                  "deep": "exhaustive (all notable items)"}[depth]
    lang_desc = {"zh": "Chinese (中文)", "en": "English",
                 "bilingual": "both Chinese and English (bilingual)"}[language]

    dim_section = "\n".join(
        f"[{d.upper()}] {prompts.get(d, DEFAULT_PROMPTS.get(d, ''))}"
        for d in dimensions
    )
    extra_section = f"\nExtra instructions: {extra}" if extra else ""
    return (
        "You are an expert literary annotator for Chinese readers learning English literature.\n"
        f"Analysis depth: {depth_desc}.\n"
        f"Explanation language: {lang_desc}.\n\n"
        "Dimensions to annotate:\n"
        f"{dim_section}"
        f"{extra_section}\n\n"
        "Return ONLY valid JSON with keys matching the dimension names. "
        "Each value is an array of objects with 'term' (string) and 'body_markdown' (string). "
        "Omit dimensions with no findings. "
        'Example: {"vocab": [{"term": "verdant", "body_markdown": "Means ..."}], "grammar": []}'
    )


async def _pre_pass_filter(chapter_id: int, paragraphs: list[dict]) -> list[int]:
    """Returns list of paragraph IDs worth annotating in this chapter."""
    para_list = "\n".join(
        f'[{p["id"]}] {p["text_en"][:200]}' for p in paragraphs
    )
    system = (
        "You are filtering paragraphs in a literary text. "
        "Return a JSON array of paragraph IDs worth annotating for language learning. "
        "Skip: dialog tags ('he said', 'she asked'), single-word lines, "
        "repeated phrases, chapter headings, very short fragments under 10 words."
    )
    user = f"Paragraphs:\n{para_list}\n\nReturn JSON array of IDs to annotate."
    raw = await call_once(system, user)
    try:
        ids = json.loads(raw)
        if isinstance(ids, list):
            return [int(i) for i in ids]
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: annotate all
    return [p["id"] for p in paragraphs]


async def run_job(job_id: int, queue: asyncio.Queue) -> None:
    """Background coroutine. Runs the full annotation job and pushes SSE events to queue."""
    async with _job_lock:
        bk.update_job(job_id, status="running", started_at="(datetime('now'))")
        # Use SQL datetime for started_at
        from app.db import get_conn
        get_conn().execute(
            "UPDATE annotation_jobs SET status='running', started_at=datetime('now') WHERE id=?",
            (job_id,)
        )

        try:
            job = bk.get_job(job_id)
            scope_chapter_nums = json.loads(job["scope_json"])
            dimensions = [d.strip() for d in job["dimensions_csv"].split(",") if d.strip()]
            prompts = json.loads(job["prompts_json"])
            system_prompt = build_system_prompt(
                dimensions, prompts, job["depth"], job["language"], job.get("extra_instructions")
            )
            prompt_hash = job["prompt_version_hash"]

            # Get all chapters for this book in scope
            all_chapters = bk.get_chapters_for_book(job["book_id"])
            chapters_in_scope = [ch for ch in all_chapters if ch["chapter_num"] in scope_chapter_nums]

            # Get all paragraphs grouped by chapter
            all_paras = bk.get_paragraphs_for_book(job["book_id"])
            paras_by_chapter: dict[int, list[dict]] = {}
            for p in all_paras:
                cid = p["chapter_id"]
                paras_by_chapter.setdefault(cid, []).append(p)

            # Count total work
            total = sum(len(paras_by_chapter.get(ch["id"], [])) for ch in chapters_in_scope)
            done = 0
            bk.update_job(job_id, progress_total=total)
            await queue.put({"type": "progress", "done": 0, "total": total})

            for ch in chapters_in_scope:
                ch_paras = paras_by_chapter.get(ch["id"], [])
                if not ch_paras:
                    continue

                # Pre-pass filter
                worth_ids = await _pre_pass_filter(ch["id"], ch_paras)
                worth_set = set(worth_ids)

                for para in ch_paras:
                    done += 1
                    if para["id"] not in worth_set:
                        await queue.put({"type": "progress", "done": done, "total": total})
                        continue

                    raw = await call_once(system_prompt, f'Paragraph: "{para["text_en"]}"')
                    try:
                        result = json.loads(raw)
                    except json.JSONDecodeError:
                        await queue.put({"type": "progress", "done": done, "total": total})
                        continue

                    for dim, items in result.items():
                        if not isinstance(items, list):
                            continue
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            term = item.get("term", "")
                            body = item.get("body_markdown", "")
                            if not term or not body:
                                continue
                            bk.upsert_annotation(
                                para["id"], dim, term, body, prompt_hash
                            )
                            await queue.put({
                                "type": "annotation",
                                "paragraph_id": para["id"],
                                "dimension": dim,
                                "term": term,
                                "body_markdown": body,
                            })

                    bk.update_job(job_id, progress_done=done)
                    await queue.put({"type": "progress", "done": done, "total": total})

            bk.update_job(job_id, status="done", progress_done=done)
            get_conn().execute(
                "UPDATE annotation_jobs SET completed_at=datetime('now') WHERE id=?", (job_id,)
            )
            await queue.put({"type": "done", "job_id": job_id})

        except DeepSeekError as e:
            bk.update_job(job_id, status="error", error_message=str(e)[:500])
            await queue.put({"type": "error", "message": str(e)[:200]})
        except Exception as e:
            bk.update_job(job_id, status="error", error_message=str(e)[:500])
            await queue.put({"type": "error", "message": str(e)[:200]})
```

- [ ] **Step 4: Run tests**

```bash
cd server && pytest tests/test_annotation_runner.py -v
```

Expected: 3/3 PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/annotation_runner.py server/tests/test_annotation_runner.py
git commit -m "feat: add annotation_runner with background worker, pre-pass filter, SSE queue"
```

---

### Task 5: admin_books routes

**Files:**
- Create: `server/app/routes/admin_books.py`
- Create: `server/tests/test_routes_admin_books.py`

- [ ] **Step 1: Write failing tests**

```python
# server/tests/test_routes_admin_books.py
import pytest
from fastapi.testclient import TestClient
from app.db import migrate, get_conn, reset_conn
from app import books as bk

@pytest.fixture
def client(env):
    reset_conn()
    migrate()
    from app.main import create_app
    return TestClient(create_app())

@pytest.fixture
def admin_client(client):
    """Client with valid admin session cookie."""
    r = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "test"})
    # Create admin user first
    from app.users import create_user
    create_user("admin@test.com", "testtest", "Admin", is_admin=True)
    r = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "testtest"})
    assert r.status_code == 200
    return client

def test_list_books_requires_admin(client):
    r = client.get("/api/admin/books")
    assert r.status_code == 401

def test_list_books_empty(admin_client):
    r = admin_client.get("/api/admin/books")
    assert r.status_code == 200
    assert r.json() == []

def test_patch_book_status(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    r = admin_client.patch(f"/api/admin/books/{book_id}", json={"status": "published"})
    assert r.status_code == 200
    assert bk.get_book(book_id)["status"] == "published"

def test_patch_book_invalid_status(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    r = admin_client.patch(f"/api/admin/books/{book_id}", json={"status": "annotating"})
    assert r.status_code == 422

def test_delete_book(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    r = admin_client.delete(f"/api/admin/books/{book_id}")
    assert r.status_code == 200
    with pytest.raises(bk.BookNotFoundError):
        bk.get_book(book_id)

def test_get_chapters(admin_client):
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    bk.add_chapter(book_id, 1, "第一章", "Chapter text.")
    r = admin_client.get(f"/api/admin/books/{book_id}/chapters")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["chapter_num"] == 1
```

- [ ] **Step 2: Run — verify fail**

```bash
cd server && pytest tests/test_routes_admin_books.py -v 2>&1 | head -15
```

Expected: FAIL (module not found)

- [ ] **Step 3: Write admin_books.py**

```python
# server/app/routes/admin_books.py
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status as hs
from pydantic import BaseModel
from typing import Literal
from app.auth import require_admin_user
from app import books as bk

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_user)])


class BookPatch(BaseModel):
    status: Literal["draft", "published"] | None = None
    cover_css: str | None = None


@router.get("/books")
def list_books():
    return bk.list_books()


@router.patch("/books/{book_id}")
def patch_book(book_id: int, body: BookPatch):
    try:
        bk.update_book(book_id, status=body.status, cover_css=body.cover_css)
    except ValueError as e:
        raise HTTPException(status_code=hs.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except bk.BookNotFoundError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)
    return {"ok": True}


@router.delete("/books/{book_id}")
def delete_book(book_id: int):
    try:
        bk.delete_book(book_id)
    except bk.BookNotFoundError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)
    return {"ok": True}


@router.get("/books/{book_id}/chapters")
def get_chapters(book_id: int):
    return bk.get_chapters_for_book(book_id)


@router.get("/books/{book_id}/paragraphs")
def get_paragraphs(book_id: int):
    return bk.get_paragraphs_for_book(book_id)


@router.get("/books/{book_id}/annotations")
def get_annotations(book_id: int):
    return bk.get_annotations_for_book(book_id)


@router.post("/books/upload")
async def upload_epub(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".epub"):
        raise HTTPException(status_code=hs.HTTP_400_BAD_REQUEST,
                            detail="File must be a .epub")
    data = await file.read()
    try:
        from app.epub_parser import parse_epub_to_db
        book_id = parse_epub_to_db(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(status_code=hs.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"EPUB parse error: {str(e)[:200]}")
    return {"book_id": book_id}
```

- [ ] **Step 4: Wire router into main.py — add import and include**

Open `server/app/main.py`. Replace the full file with:

```python
from fastapi import FastAPI
from app.db import migrate
from app.routes import admin, notes, query
from app.routes import auth as auth_routes
from app.routes import user_notes as user_notes_routes
from app.routes import progress as progress_routes
from app.routes import admin_books as admin_books_routes
from app.routes import admin_jobs as admin_jobs_routes

def create_app() -> FastAPI:
    migrate()
    from app import books as bk
    bk.reset_stale_jobs()
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    app.include_router(query.router)
    app.include_router(auth_routes.router)
    app.include_router(user_notes_routes.router)
    app.include_router(progress_routes.router)
    app.include_router(admin_books_routes.router)
    app.include_router(admin_jobs_routes.router)
    return app

try:
    app = create_app()
except Exception:
    app = None
```

- [ ] **Step 5: Run tests**

```bash
cd server && pytest tests/test_routes_admin_books.py -v
```

Expected: all PASS (skip upload test — epub_parser not yet written)

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/admin_books.py server/tests/test_routes_admin_books.py server/app/main.py
git commit -m "feat: add admin books API routes (list, patch, delete, chapters, paragraphs, annotations)"
```

---

### Task 6: admin_jobs routes + SSE streaming

**Files:**
- Create: `server/app/routes/admin_jobs.py`
- Create: `server/tests/test_routes_admin_jobs.py`

- [ ] **Step 1: Write failing tests**

```python
# server/tests/test_routes_admin_jobs.py
import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from app.db import migrate, reset_conn
from app import books as bk
from app.users import create_user

@pytest.fixture
def client(env):
    reset_conn()
    migrate()
    create_user("admin@test.com", "testtest", "Admin", is_admin=True)
    book_id = bk.create_book("great-gatsby", "The Great Gatsby", "了不起的盖茨比", "F. Scott Fitzgerald")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "Chapter text.")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    bk.add_paragraph(sec_id, 1, "In my younger years.")
    from app.main import create_app
    c = TestClient(create_app())
    r = c.post("/api/auth/login", json={"email": "admin@test.com", "password": "testtest"})
    assert r.status_code == 200
    return c, book_id

def test_create_job(client):
    c, book_id = client
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

def test_get_job_status(client):
    c, book_id = client
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
```

- [ ] **Step 2: Run — verify fail**

```bash
cd server && pytest tests/test_routes_admin_jobs.py -v 2>&1 | head -15
```

- [ ] **Step 3: Write admin_jobs.py**

```python
# server/app/routes/admin_jobs.py
import asyncio
import json
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status as hs
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.auth import require_admin_user
from app import books as bk
from app.annotation_runner import build_system_prompt, compute_prompt_hash, run_job

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_user)])

# job_id → asyncio.Queue for SSE consumers
_job_queues: dict[int, asyncio.Queue] = {}


class JobBody(BaseModel):
    book_id: int
    scope_chapter_nums: list[int]
    dimensions: list[str]
    prompts: dict[str, str]
    depth: str = "standard"
    language: str = "zh"
    extra_instructions: str | None = None


@router.post("/jobs")
async def create_job(body: JobBody):
    system_prompt = build_system_prompt(
        body.dimensions, body.prompts, body.depth, body.language, body.extra_instructions
    )
    prompt_hash = compute_prompt_hash(system_prompt)
    job_id = bk.get_or_create_job(
        book_id=body.book_id,
        scope_json=json.dumps(body.scope_chapter_nums),
        dimensions_csv=",".join(body.dimensions),
        prompts_json=json.dumps(body.prompts),
        depth=body.depth,
        language=body.language,
        extra_instructions=body.extra_instructions,
        prompt_version_hash=prompt_hash,
    )
    queue: asyncio.Queue = asyncio.Queue()
    _job_queues[job_id] = queue
    asyncio.create_task(run_job(job_id, queue))
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    try:
        return bk.get_job(job_id)
    except LookupError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int, _=Depends(require_admin_user)):
    queue = _job_queues.get(job_id)
    if queue is None:
        # Job may have already completed — return its status
        try:
            job = bk.get_job(job_id)
        except LookupError:
            raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)
        async def done_stream():
            yield f"data: {json.dumps({'type': 'done', 'job_id': job_id})}\n\n"
        return StreamingResponse(done_stream(), media_type="text/event-stream")

    async def generate():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") in ("done", "error"):
                _job_queues.pop(job_id, None)
                break

    return StreamingResponse(generate(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: int):
    _job_queues.pop(job_id, None)
    try:
        bk.update_job(job_id, status="error", error_message="cancelled by admin")
    except LookupError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)
    return {"ok": True}
```

- [ ] **Step 4: Run all tests**

```bash
cd server && pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests pass + new job tests pass

- [ ] **Step 5: Commit**

```bash
git add server/app/routes/admin_jobs.py server/tests/test_routes_admin_jobs.py
git commit -m "feat: add admin jobs API routes with SSE streaming"
```

---

### Task 7: EPUB parser + pyproject.toml dependencies

**Files:**
- Create: `server/app/epub_parser.py`
- Modify: `server/pyproject.toml`

- [ ] **Step 1: Add ebooklib and bs4 to pyproject.toml**

In `server/pyproject.toml`, add to the `dependencies` list:

```toml
  "ebooklib==0.18.*",
  "beautifulsoup4==4.12.*",
  "lxml>=4.9",
```

- [ ] **Step 2: Install in venv**

```bash
cd server && pip install ebooklib==0.18.* beautifulsoup4==4.12.* lxml
```

Expected: installs without error

- [ ] **Step 3: Write epub_parser.py**

```python
# server/app/epub_parser.py
"""Parse an EPUB file and insert book/chapter/section/paragraph rows into the DB."""
from __future__ import annotations
import io
import re
import warnings
from pathlib import Path
from typing import BinaryIO

# Suppress ebooklib's verbose warnings about missing/optional fields
warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from app import books as bk


def _clean_text(html: str) -> list[str]:
    """Extract non-empty paragraph texts from HTML."""
    soup = BeautifulSoup(html, "lxml")
    texts = []
    for tag in soup.find_all(["p", "div"]):
        t = tag.get_text(" ", strip=True)
        if t and len(t) > 10:
            texts.append(t)
    return texts


def parse_epub_to_db(fileobj: BinaryIO) -> int:
    """Parse EPUB from file-like object. Returns book_id."""
    book = epub.read_epub(fileobj)

    title_en = book.get_metadata("DC", "title")
    title_en = title_en[0][0] if title_en else "Unknown Title"

    creator = book.get_metadata("DC", "creator")
    author = creator[0][0] if creator else "Unknown Author"

    # Derive slug from title
    slug = re.sub(r"[^a-z0-9]+", "-", title_en.lower()).strip("-")[:50]

    # Ensure slug is unique
    base_slug = slug
    i = 1
    while True:
        try:
            book_id = bk.create_book(slug, title_en, title_en, author)
            break
        except bk.BookExistsError:
            slug = f"{base_slug}-{i}"
            i += 1

    # Parse spine items as chapters
    chapter_num = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html = item.get_content().decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        body_text = soup.get_text(" ", strip=True)
        if len(body_text) < 50:
            continue  # skip nav/toc pages

        chapter_num += 1
        # Use h1/h2 as chapter title if present
        h = soup.find(["h1", "h2"])
        title_zh = h.get_text(strip=True) if h else f"第{chapter_num}章"

        ch_id = bk.add_chapter(book_id, chapter_num, title_zh, body_text)

        # Split into sections by h2/h3 markers
        sections: list[list[str]] = []
        current: list[str] = []
        for tag in soup.body.children if soup.body else []:
            if hasattr(tag, "name") and tag.name in ("h2", "h3"):
                if current:
                    sections.append(current)
                    current = []
            elif hasattr(tag, "name") and tag.name == "p":
                t = tag.get_text(" ", strip=True)
                if t and len(t) > 10:
                    current.append(t)
        if current:
            sections.append(current)

        if not sections:
            sections = [_clean_text(html)]

        for sec_num, para_texts in enumerate(sections, 1):
            sec_id = bk.add_section(ch_id, sec_num)
            for para_num, text in enumerate(para_texts, 1):
                bk.add_paragraph(sec_id, para_num, text)

    return book_id
```

- [ ] **Step 4: Smoke-test the parser locally with a small EPUB**

If you don't have an EPUB handy, create a minimal one:

```bash
cd server
python -c "
import io, zipfile, os, tempfile
# Create a minimal EPUB zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as zf:
    zf.writestr('mimetype', 'application/epub+zip')
    zf.writestr('META-INF/container.xml', '''<?xml version=\"1.0\"?>
<container version=\"1.0\" xmlns=\"urn:oasis:schemas:container\">
  <rootfiles><rootfile full-path=\"content.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles>
</container>''')
    zf.writestr('content.opf', '''<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\">
  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
  <manifest><item id=\"ch1\" href=\"ch1.html\" media-type=\"application/xhtml+xml\"/></manifest>
  <spine><itemref idref=\"ch1\"/></spine>
</package>''')
    zf.writestr('ch1.html', '<html><body><h1>Chapter One</h1><p>In the beginning there was darkness and light.</p><p>The world was new and full of possibility.</p></body></html>')
buf.seek(0)

import sys; sys.path.insert(0, '.')
import os; os.environ.update({'BELOWICEBERG_DATA_DIR':'/tmp/epub-test','ADMIN_PASSWORD_HASH':'x','SESSION_SECRET':'x','DEEPSEEK_API_KEY':'x'})
from app.db import migrate, reset_conn; reset_conn(); migrate()
from app.epub_parser import parse_epub_to_db
book_id = parse_epub_to_db(buf)
from app import books as bk
paras = bk.get_paragraphs_for_book(book_id)
print('book_id:', book_id, 'paragraphs:', len(paras))
assert len(paras) >= 2
print('OK')
"
```

Expected: `book_id: 1 paragraphs: 2` (or more) followed by `OK`

- [ ] **Step 5: Commit**

```bash
git add server/app/epub_parser.py server/pyproject.toml
git commit -m "feat: add EPUB parser (ebooklib + bs4) for book upload flow"
```

---

### Task 8: Seed Gatsby from HTML

**Files:**
- Create: `server/scripts/seed_gatsby.py`

This script parses `gatsby-teaching-edition.html`, extracts each chapter's `para-section` elements, and seeds the database on the live server.

- [ ] **Step 1: Write the seed script**

```python
#!/usr/bin/env python3
"""
Seed the Great Gatsby book into the DB from gatsby-teaching-edition.html.
Run once on the server after the 002_books.sql migration.

Usage:
    python server/scripts/seed_gatsby.py /path/to/gatsby-teaching-edition.html
"""
import sys
import os
from pathlib import Path

# Load env from /etc/belowiceberg/admin.env on server, or from shell env locally
if Path("/etc/belowiceberg/admin.env").exists():
    for line in Path("/etc/belowiceberg/admin.env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

if not os.environ.get("BELOWICEBERG_DATA_DIR"):
    print("ERROR: BELOWICEBERG_DATA_DIR not set")
    sys.exit(1)

# Add server/ to path
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from bs4 import BeautifulSoup
from app.db import migrate, get_conn, reset_conn
from app import books as bk

GATSBY_HTML = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent / "gatsby-teaching-edition.html"
if not GATSBY_HTML.exists():
    print(f"ERROR: file not found: {GATSBY_HTML}")
    sys.exit(1)

CHAPTER_TITLES_ZH = {
    1: "第一章 · 尼克的世界",
    2: "第二章 · 灰烬谷",
    3: "第三章 · 盖茨比的派对",
    4: "第四章 · 过去的秘密",
    5: "第五章 · 重逢",
    6: "第六章 · 真相",
    7: "第七章 · 决裂",
    8: "第八章 · 死亡",
    9: "第九章 · 结局",
}

reset_conn()
migrate()
conn = get_conn()

# Check if already seeded
if conn.execute("SELECT 1 FROM books WHERE slug='great-gatsby'").fetchone():
    print("Gatsby already seeded. Exiting.")
    sys.exit(0)

soup = BeautifulSoup(GATSBY_HTML.read_text(encoding="utf-8"), "lxml")

COVER_CSS = (
    "background:linear-gradient(135deg,#1a1a2e 0%,#16213e 40%,#0f3460 70%,#533483 100%);"
    "position:relative;"
)

book_id = bk.create_book(
    slug="great-gatsby",
    title_en="The Great Gatsby",
    title_zh="了不起的盖茨比",
    author="F. Scott Fitzgerald",
    cover_css=COVER_CSS,
)
print(f"Created book id={book_id}")

for ch_num in range(1, 10):
    chapter_div = soup.find("div", {"data-chapter": str(ch_num)})
    if not chapter_div:
        print(f"  WARNING: chapter {ch_num} not found")
        continue

    # Collect all paragraph text from .original p tags in this chapter
    sections_html = chapter_div.find_all("section", class_="para-section")

    # Full text = join all original paragraphs
    all_para_texts = []
    for sec in sections_html:
        orig = sec.find("div", class_="original")
        if orig:
            for p in orig.find_all("p"):
                t = p.get_text(" ", strip=True)
                if t:
                    all_para_texts.append(t)

    text_full = "\n\n".join(all_para_texts)
    title_zh = CHAPTER_TITLES_ZH.get(ch_num, f"第{ch_num}章")
    ch_id = bk.add_chapter(book_id, ch_num, title_zh, text_full)
    print(f"  Chapter {ch_num}: {len(sections_html)} sections")

    for sec_num, sec_el in enumerate(sections_html, 1):
        # Section title from sec-heading
        heading_el = sec_el.find("span", class_="sec-label")
        sec_title = heading_el.get_text(strip=True) if heading_el else None

        sec_id = bk.add_section(ch_id, sec_num, sec_title)

        orig = sec_el.find("div", class_="original")
        if not orig:
            continue

        para_num = 0
        for p in orig.find_all("p"):
            t = p.get_text(" ", strip=True)
            if t and len(t) > 5:
                para_num += 1
                bk.add_paragraph(sec_id, para_num, t)

print(f"\nDone. book_id={book_id}")
paras = bk.get_paragraphs_for_book(book_id)
print(f"Total paragraphs seeded: {len(paras)}")
```

- [ ] **Step 2: Test locally**

```bash
cd server
BELOWICEBERG_DATA_DIR=/tmp/gatsby-seed \
  ADMIN_PASSWORD_HASH='$2b$12$YJTEgo/E1vhvLDoU.YZejeUU3DDmm6kQuH1/Ko7kg34a/RlgMX1oa' \
  SESSION_SECRET=test DEEPSEEK_API_KEY=sk-test \
  python scripts/seed_gatsby.py ../gatsby-teaching-edition.html
```

Expected output:
```
Created book id=1
  Chapter 1: 17 sections
  Chapter 2: 5 sections
  ...
Done. book_id=1
Total paragraphs seeded: ~400+
```

- [ ] **Step 3: Commit**

```bash
git add server/scripts/seed_gatsby.py
git commit -m "feat: add seed_gatsby.py to populate Gatsby chapters/sections/paragraphs from HTML"
```

---

### Task 9: Admin dashboard frontend

**Files:**
- Create: `admin/index.html`
- Create: `admin/styles.css`

- [ ] **Step 1: Write admin/styles.css**

```css
/* admin/styles.css */
:root {
  --bg: #fafaf7; --bg2: #f2efe7; --bg3: #e8e4d8; --bg4: #ded9cb;
  --gold: #b8942e; --gold-pale: rgba(184,148,46,0.08); --gold-dim: rgba(184,148,46,0.4);
  --text: #2d2a20; --text2: #6b5e3e; --text3: #a89870; --ink: #1a1a15;
  --border: rgba(184,148,46,0.25); --r: 8px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: 'Lora', serif; min-height: 100vh; }
a { color: var(--gold); text-decoration: none; }

.admin-wrap { max-width: 960px; margin: 0 auto; padding: 2rem 1rem; }

/* Header */
.admin-header { display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 0.5px solid var(--border); }
.admin-header h1 { font-family: 'Playfair Display', serif; font-size: 1.6rem; }
.admin-badge { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;
  background: var(--bg3); color: var(--text2); padding: 2px 8px;
  border-radius: 4px; letter-spacing: 0.08em; margin-left: 0.75rem; }

/* Buttons */
.btn-primary { background: var(--gold); color: #fff; border: none; cursor: pointer;
  padding: 0.55rem 1.1rem; border-radius: var(--r); font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem; letter-spacing: 0.04em; }
.btn-primary:hover { opacity: 0.88; }
.btn-sm { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
  padding: 0.3rem 0.7rem; border-radius: 5px; border: 0.5px solid var(--border);
  background: transparent; color: var(--text2); cursor: pointer; }
.btn-sm.btn-primary { background: var(--gold); color: #fff; border-color: var(--gold); }

/* Upload zone */
.upload-zone { margin-bottom: 1.5rem; }
.drop-target { border: 1.5px dashed var(--border); border-radius: var(--r);
  padding: 2rem; text-align: center; color: var(--text2); background: var(--bg2); }
.drop-target.drag-over { border-color: var(--gold); background: var(--gold-pale); }
.file-label { color: var(--gold); cursor: pointer; text-decoration: underline; }
.progress-bar { height: 4px; background: var(--bg3); border-radius: 2px; margin: 1rem 0 0.5rem; }
.progress-fill { height: 100%; background: var(--gold); border-radius: 2px;
  width: 0%; transition: width 0.3s; }
.hidden { display: none !important; }

/* Filter row */
.filter-row { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }
.book-count { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--text3); }
.filter-pills { display: flex; gap: 0.4rem; }
.pill { padding: 0.3rem 0.8rem; border-radius: 99px; font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem; border: 0.5px solid var(--border); background: transparent;
  color: var(--text2); cursor: pointer; }
.pill.active { background: var(--gold); color: #fff; border-color: var(--gold); }

/* Book list */
.book-row { display: grid;
  grid-template-columns: 40px 1fr auto auto auto;
  gap: 1rem; align-items: center;
  padding: 0.85rem 0;
  border-bottom: 0.5px solid var(--border); }
.book-cover-mini { width: 40px; height: 54px; border-radius: 4px; flex-shrink: 0; }
.book-title-en { font-family: 'Playfair Display', serif; font-size: 0.95rem; }
.book-title-zh { font-family: 'Noto Serif SC', serif; font-size: 0.8rem; color: var(--text2); }
.book-meta { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--text3); margin-top: 2px; }
.book-progress { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: var(--text3); white-space: nowrap; }
.status-badge { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; letter-spacing: 0.06em;
  padding: 3px 8px; border-radius: 4px; cursor: pointer; border: 0.5px solid var(--border); }
.status-draft { background: var(--bg3); color: var(--text2); }
.status-published { background: var(--gold-pale); color: var(--gold); border-color: var(--gold-dim); }
.book-actions { display: flex; gap: 0.4rem; }
.empty, .loading { text-align: center; color: var(--text3); padding: 2rem;
  font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }

@media (max-width: 600px) {
  .book-row { grid-template-columns: 40px 1fr auto; }
  .book-progress, .book-actions { display: none; }
}
```

- [ ] **Step 2: Write admin/index.html**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>管理后台 · B社</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=Lora:wght@400;500&family=Noto+Serif+SC:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/admin/styles.css">
</head>
<body>
<div class="admin-wrap">
  <div class="admin-header">
    <div style="display:flex;align-items:center;gap:0.5rem">
      <h1>管理后台</h1>
      <span class="admin-badge">ADMIN</span>
    </div>
    <button id="upload-toggle" class="btn-primary">+ 上传新书</button>
  </div>

  <div id="upload-zone" class="upload-zone hidden">
    <div class="drop-target" id="drop-target">
      <p style="margin-bottom:0.5rem">拖放 EPUB 文件到这里，或
        <label for="file-input" class="file-label">点击选择</label>
      </p>
      <input type="file" id="file-input" accept=".epub" hidden>
      <div id="upload-progress" class="hidden" style="max-width:320px;margin:0 auto">
        <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
        <p id="upload-status" style="font-size:0.8rem;color:var(--text2)"></p>
      </div>
    </div>
  </div>

  <div class="filter-row">
    <span id="book-count" class="book-count">载入中…</span>
    <div class="filter-pills">
      <button class="pill active" data-filter="all">全部</button>
      <button class="pill" data-filter="draft">草稿</button>
      <button class="pill" data-filter="published">已发布</button>
    </div>
  </div>

  <div id="book-list"></div>
</div>

<script>
let allBooks = [];
let currentFilter = 'all';

// Auth check
fetch('/api/me').then(r => {
  if (!r.ok) { location.href = '/login/?next=/admin/'; return null; }
  return r.json();
}).then(user => {
  if (!user) return;
  if (!user.is_admin) { location.href = '/'; return; }
  loadBooks();
}).catch(() => { location.href = '/login/?next=/admin/'; });

async function loadBooks() {
  const r = await fetch('/api/admin/books');
  if (!r.ok) return;
  allBooks = await r.json();
  renderBooks();
}

function renderBooks() {
  const filtered = currentFilter === 'all' ? allBooks
    : allBooks.filter(b => b.status === currentFilter);
  document.getElementById('book-count').textContent = `${filtered.length} 本书`;
  const el = document.getElementById('book-list');
  if (!filtered.length) {
    el.innerHTML = '<p class="empty">暂无书籍</p>';
    return;
  }
  el.innerHTML = filtered.map(bookRow).join('');
}

function bookRow(b) {
  return `
    <div class="book-row">
      <div class="book-cover-mini" style="${b.cover_css || 'background:var(--bg3)'}"></div>
      <div class="book-info">
        <div class="book-title-en">${b.title_en}</div>
        <div class="book-title-zh">${b.title_zh}</div>
        <div class="book-meta">${b.author} · ${b.chapter_count} 章</div>
      </div>
      <div class="book-progress">${b.annotated_paragraphs} / ${b.total_paragraphs} 段已标注</div>
      <button class="status-badge status-${b.status}" onclick="toggleStatus(${b.id},'${b.status}')">
        ${b.status === 'published' ? 'PUBLISHED' : 'DRAFT'}
      </button>
      <div class="book-actions">
        <a href="/gatsby" target="_blank" class="btn-sm">预览</a>
        <a href="/admin/edit/?book=${b.id}" class="btn-sm btn-primary">标注</a>
      </div>
    </div>`;
}

async function toggleStatus(id, current) {
  const next = current === 'published' ? 'draft' : 'published';
  await fetch(`/api/admin/books/${id}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({status: next})
  });
  loadBooks();
}

document.querySelectorAll('.pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    renderBooks();
  });
});

document.getElementById('upload-toggle').addEventListener('click', () => {
  document.getElementById('upload-zone').classList.toggle('hidden');
});

const drop = document.getElementById('drop-target');
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag-over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('drag-over'));
drop.addEventListener('drop', e => {
  e.preventDefault(); drop.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) uploadEpub(e.dataTransfer.files[0]);
});
document.getElementById('file-input').addEventListener('change', e => {
  if (e.target.files[0]) uploadEpub(e.target.files[0]);
});

async function uploadEpub(file) {
  const prog = document.getElementById('upload-progress');
  const status = document.getElementById('upload-status');
  const fill = document.getElementById('progress-fill');
  prog.classList.remove('hidden');
  status.textContent = '正在上传和解析…';
  fill.style.width = '30%';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch('/api/admin/books/upload', {method:'POST', body: fd});
    if (!r.ok) throw new Error(await r.text());
    fill.style.width = '100%';
    const data = await r.json();
    status.textContent = '上传成功！正在跳转…';
    await loadBooks();
    setTimeout(() => location.href = `/admin/edit/?book=${data.book_id}`, 800);
  } catch(err) {
    status.textContent = `上传失败：${err.message.slice(0,100)}`;
    fill.style.width = '0%';
  }
}
</script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add admin/index.html admin/styles.css
git commit -m "feat: add admin dashboard page (book list, upload zone, status toggle)"
```

---

### Task 10: Admin annotation editor frontend

**Files:**
- Create: `admin/edit/index.html`
- Create: `admin/edit/styles.css`

- [ ] **Step 1: Write admin/edit/styles.css**

```css
/* admin/edit/styles.css */
:root {
  --bg: #fafaf7; --bg2: #f2efe7; --bg3: #e8e4d8; --bg4: #ded9cb;
  --gold: #b8942e; --gold-pale: rgba(184,148,46,0.08); --gold-dim: rgba(184,148,46,0.4);
  --text: #2d2a20; --text2: #6b5e3e; --text3: #a89870; --ink: #1a1a15;
  --border: rgba(184,148,46,0.25); --r: 8px;
  --vocab: #3a7bb5; --gram: #3a8b5e; --syntax: #7a4f9b;
  --lit: #c45a3a; --cult: #3a7a8b; --style-c: #7a7a3a;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: 'Lora', serif;
  height: 100vh; overflow: hidden; }

/* Two-pane layout */
.editor-layout { display: grid; grid-template-columns: 55% 45%; height: 100vh; }

/* Left pane */
.left-pane { overflow-y: auto; border-right: 0.5px solid var(--border); }
.left-header { position: sticky; top: 0; background: var(--bg); z-index: 10;
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 1.5rem; border-bottom: 0.5px solid var(--border); gap: 1rem; }
.left-header-back { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;
  color: var(--text3); }
.left-header-title { flex: 1; }
.left-header-title .title-en { font-family: 'Playfair Display', serif; font-size: 1rem; }
.left-header-title .title-zh { font-family: 'Noto Serif SC', serif; font-size: 0.8rem; color: var(--text2); }
.btn-annotate { background: var(--gold); color: #fff; border: none; cursor: pointer;
  padding: 0.5rem 1rem; border-radius: var(--r); font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem; white-space: nowrap; }
.btn-annotate:disabled { opacity: 0.5; cursor: not-allowed; }

/* Paragraph rendering */
.para-block { padding: 1rem 1.5rem; border-bottom: 0.5px solid var(--border); cursor: pointer; }
.para-block:hover { background: var(--gold-pale); }
.para-block.active { background: var(--gold-pale); }
.para-text { font-family: 'Lora', serif; font-size: 0.95rem; line-height: 1.75;
  color: var(--ink); }
.para-meta { font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: var(--text3);
  margin-bottom: 0.4rem; }
.chapter-divider { padding: 1rem 1.5rem 0.5rem;
  font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;
  color: var(--text3); letter-spacing: 0.1em; text-transform: uppercase;
  border-top: 0.5px solid var(--border); margin-top: 0.5rem; }

/* Annotation cards in left pane */
.ann-cards { padding: 0.5rem 1.5rem 1rem; display: flex; flex-direction: column; gap: 0.5rem; }
.ann-card { background: var(--bg2); border-radius: var(--r); padding: 0.6rem 0.8rem;
  border-left: 3px solid var(--border); }
.ann-card[data-dim="vocab"]   { border-left-color: var(--vocab); }
.ann-card[data-dim="grammar"] { border-left-color: var(--gram); }
.ann-card[data-dim="syntax"]  { border-left-color: var(--syntax); }
.ann-card[data-dim="lit"]     { border-left-color: var(--lit); }
.ann-card[data-dim="cult"]    { border-left-color: var(--cult); }
.ann-card[data-dim="style"]   { border-left-color: var(--style-c); }
.ann-card-term { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;
  font-weight: 500; color: var(--text); margin-bottom: 0.25rem; }
.ann-card-body { font-size: 0.82rem; color: var(--text2); line-height: 1.55; }

/* Right pane */
.right-pane { overflow-y: auto; background: var(--bg2); }
.right-section { padding: 1.2rem 1.5rem; border-bottom: 0.5px solid var(--border); }
.right-section-hdr { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;
  color: var(--text3); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.8rem; }

/* Scope list */
.scope-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.35rem 0;
  font-size: 0.85rem; cursor: pointer; }
.scope-row input[type=checkbox] { accent-color: var(--gold); }
.scope-title { flex: 1; font-family: 'Noto Serif SC', serif; font-size: 0.82rem; }
.scope-progress { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--text3); }
.scope-all { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: var(--text3);
  padding-top: 0.5rem; cursor: pointer; text-decoration: underline; }

/* Dimension tags */
.dim-tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.8rem; }
.dim-tag { padding: 0.3rem 0.7rem; border-radius: 99px; font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem; cursor: pointer; border: 1.5px solid; opacity: 0.45; }
.dim-tag.on { opacity: 1; color: #fff; }
.dim-tag[data-d="vocab"]   { color: var(--vocab); border-color: var(--vocab); }
.dim-tag[data-d="grammar"] { color: var(--gram);  border-color: var(--gram); }
.dim-tag[data-d="syntax"]  { color: var(--syntax);border-color: var(--syntax); }
.dim-tag[data-d="lit"]     { color: var(--lit);   border-color: var(--lit); }
.dim-tag[data-d="cult"]    { color: var(--cult);  border-color: var(--cult); }
.dim-tag[data-d="style"]   { color: var(--style-c);border-color: var(--style-c); }
.dim-tag.on[data-d="vocab"]   { background: var(--vocab); }
.dim-tag.on[data-d="grammar"] { background: var(--gram); }
.dim-tag.on[data-d="syntax"]  { background: var(--syntax); }
.dim-tag.on[data-d="lit"]     { background: var(--lit); }
.dim-tag.on[data-d="cult"]    { background: var(--cult); }
.dim-tag.on[data-d="style"]   { background: var(--style-c); }

.prompt-editor { margin-top: 0.5rem; }
.prompt-toggle { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem;
  color: var(--text3); cursor: pointer; background: none; border: none;
  padding: 0; margin-bottom: 0.3rem; }
.prompt-textarea { width: 100%; padding: 0.5rem; font-size: 0.78rem; font-family: 'Lora', serif;
  background: var(--bg); border: 0.5px solid var(--border); border-radius: 5px;
  resize: vertical; min-height: 70px; color: var(--text); }

/* Depth/Language radios */
.radio-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.radio-opt { display: flex; align-items: center; gap: 0.3rem;
  font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; cursor: pointer; }
.radio-opt input { accent-color: var(--gold); }

/* Prompt preview */
.prompt-preview { font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
  background: var(--bg); padding: 0.8rem; border-radius: 5px; color: var(--text2);
  white-space: pre-wrap; word-break: break-word; border: 0.5px solid var(--border);
  max-height: 200px; overflow-y: auto; }

/* Extra textarea */
.extra-textarea { width: 100%; padding: 0.5rem; font-size: 0.78rem; font-family: 'Lora', serif;
  background: var(--bg); border: 0.5px solid var(--border); border-radius: 5px;
  resize: vertical; min-height: 60px; color: var(--text); }

@media (max-width: 700px) {
  .editor-layout { grid-template-columns: 1fr; grid-template-rows: 50vh 50vh; }
  .left-pane, .right-pane { height: 50vh; overflow-y: auto; }
  body { height: auto; overflow: auto; }
}
```

- [ ] **Step 2: Write admin/edit/index.html**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>标注编辑器 · B社</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=Lora:ital,wght@0,400;0,500;1,400&family=Noto+Serif+SC:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/admin/edit/styles.css">
</head>
<body>
<div class="editor-layout">
  <!-- LEFT PANE -->
  <div class="left-pane" id="left-pane">
    <div class="left-header">
      <a href="/admin/" class="left-header-back">← 返回</a>
      <div class="left-header-title">
        <div class="title-en" id="book-title-en">载入中…</div>
        <div class="title-zh" id="book-title-zh"></div>
      </div>
      <button class="btn-annotate" id="btn-annotate" onclick="startAnnotation()">开始标注</button>
    </div>
    <div id="paragraphs-container"></div>
  </div>

  <!-- RIGHT PANE -->
  <div class="right-pane" id="right-pane">
    <!-- Scope -->
    <div class="right-section">
      <div class="right-section-hdr">SCOPE · 标注范围</div>
      <div id="scope-list"></div>
      <div class="scope-all" onclick="toggleAllScope()">整本书 · 全部章节 ↕</div>
    </div>

    <!-- Dimensions -->
    <div class="right-section">
      <div class="right-section-hdr">DIMENSIONS · 标注维度</div>
      <div class="dim-tags">
        <span class="dim-tag on" data-d="vocab" onclick="toggleDim(this)">词汇</span>
        <span class="dim-tag on" data-d="grammar" onclick="toggleDim(this)">语法</span>
        <span class="dim-tag" data-d="syntax" onclick="toggleDim(this)">句法</span>
        <span class="dim-tag" data-d="lit" onclick="toggleDim(this)">文学手法</span>
        <span class="dim-tag" data-d="cult" onclick="toggleDim(this)">文化背景</span>
        <span class="dim-tag" data-d="style" onclick="toggleDim(this)">风格分析</span>
      </div>
      <div id="prompt-editors"></div>
    </div>

    <!-- Depth & Language -->
    <div class="right-section">
      <div class="right-section-hdr">SETTINGS · 深度与语言</div>
      <p style="font-family:'JetBrains Mono',monospace;font-size:0.7rem;color:var(--text3);margin-bottom:0.4rem">深度</p>
      <div class="radio-row" style="margin-bottom:0.8rem">
        <label class="radio-opt"><input type="radio" name="depth" value="light"> 简读</label>
        <label class="radio-opt"><input type="radio" name="depth" value="standard" checked> 标准</label>
        <label class="radio-opt"><input type="radio" name="depth" value="deep"> 深度</label>
      </div>
      <p style="font-family:'JetBrains Mono',monospace;font-size:0.7rem;color:var(--text3);margin-bottom:0.4rem">语言</p>
      <div class="radio-row">
        <label class="radio-opt"><input type="radio" name="language" value="zh" checked> 中文</label>
        <label class="radio-opt"><input type="radio" name="language" value="en"> English</label>
        <label class="radio-opt"><input type="radio" name="language" value="bilingual"> 双语</label>
      </div>
    </div>

    <!-- Extra instructions -->
    <div class="right-section">
      <div class="right-section-hdr">EXTRA · 补充指令</div>
      <textarea id="extra-instructions" class="extra-textarea"
        placeholder="例如：重点关注比喻和讽刺手法…"></textarea>
    </div>

    <!-- Prompt preview -->
    <div class="right-section">
      <div class="right-section-hdr">PREVIEW · 提示词预览</div>
      <pre class="prompt-preview" id="prompt-preview">选择维度后预览将在此显示</pre>
    </div>
  </div>
</div>

<script>
const DEFAULT_PROMPTS = {
  vocab:   "Identify vocabulary worth teaching: unusual words, literary diction, words used in unexpected ways. For each, write a 2-3 sentence explanation in the target language.",
  grammar: "Identify grammatical structures worth teaching: tenses, passive voice, complex clauses. Explain the structure and why it matters here.",
  syntax:  "Identify syntactic patterns worth teaching: sentence length, inversion, parallelism, fragmentation. Explain the effect.",
  lit:     "Identify literary devices: metaphor, simile, irony, foreshadowing, allusion. Explain the device and its effect.",
  cult:    "Identify cultural references: historical events, geography, social customs, period details. Explain what a non-Western reader needs to know.",
  style:   "Identify stylistic choices: register, tone, rhythm, word choice. Explain what they reveal about the narrator or characters.",
};

const params = new URLSearchParams(location.search);
const BOOK_ID = parseInt(params.get('book') || '0');
if (!BOOK_ID) { alert('Missing book param'); location.href = '/admin/'; }

let bookData = null;
let chapters = [];
let paragraphs = [];
let annotations = {}; // paragraph_id → [{dimension, term, body_markdown}]
let scopeChapterNums = new Set();

// Auth check
fetch('/api/me').then(r => r.ok ? r.json() : null).then(user => {
  if (!user || !user.is_admin) { location.href = '/login/?next=/admin/edit/?book=' + BOOK_ID; return; }
  loadEditor();
}).catch(() => { location.href = '/login/'; });

async function loadEditor() {
  const [bRes, chRes, pRes, aRes] = await Promise.all([
    fetch(`/api/admin/books`),
    fetch(`/api/admin/books/${BOOK_ID}/chapters`),
    fetch(`/api/admin/books/${BOOK_ID}/paragraphs`),
    fetch(`/api/admin/books/${BOOK_ID}/annotations`),
  ]);
  const books = await bRes.json();
  bookData = books.find(b => b.id === BOOK_ID);
  if (!bookData) { alert('Book not found'); location.href = '/admin/'; return; }
  document.getElementById('book-title-en').textContent = bookData.title_en;
  document.getElementById('book-title-zh').textContent = bookData.title_zh;

  chapters = await chRes.json();
  paragraphs = await pRes.json();

  const annList = await aRes.json();
  annotations = {};
  for (const a of annList) {
    (annotations[a.paragraph_id] = annotations[a.paragraph_id] || []).push(a);
  }

  // Default scope: all chapters
  scopeChapterNums = new Set(chapters.map(c => c.chapter_num));

  renderScopeList();
  renderParagraphs();
  renderPromptEditors();
  updatePromptPreview();

  document.querySelectorAll('input[name=depth], input[name=language]').forEach(r => {
    r.addEventListener('change', updatePromptPreview);
  });
  document.getElementById('extra-instructions').addEventListener('input', updatePromptPreview);
}

function renderScopeList() {
  const el = document.getElementById('scope-list');
  el.innerHTML = chapters.map(ch => `
    <div class="scope-row" onclick="toggleScope(${ch.chapter_num}, this)">
      <input type="checkbox" ${scopeChapterNums.has(ch.chapter_num) ? 'checked' : ''}
             onchange="toggleScope(${ch.chapter_num}, this.closest('.scope-row'))">
      <span class="scope-title">${ch.title_zh}</span>
      <span class="scope-progress">${ch.annotated_paragraphs}/${ch.total_paragraphs}</span>
    </div>
  `).join('');
}

function toggleScope(chNum, row) {
  const cb = row.querySelector('input[type=checkbox]');
  if (event.target !== cb) cb.checked = !cb.checked;
  if (cb.checked) scopeChapterNums.add(chNum); else scopeChapterNums.delete(chNum);
  updatePromptPreview();
}

function toggleAllScope() {
  const allChecked = scopeChapterNums.size === chapters.length;
  if (allChecked) scopeChapterNums.clear();
  else chapters.forEach(c => scopeChapterNums.add(c.chapter_num));
  renderScopeList();
  updatePromptPreview();
}

function toggleDim(tag) {
  tag.classList.toggle('on');
  renderPromptEditors();
  updatePromptPreview();
}

function renderPromptEditors() {
  const activeDims = [...document.querySelectorAll('.dim-tag.on')].map(t => t.dataset.d);
  const el = document.getElementById('prompt-editors');
  el.innerHTML = activeDims.map(d => `
    <div class="prompt-editor" id="pe-${d}">
      <button class="prompt-toggle" onclick="togglePromptExpand('${d}')">展开编辑 ▾</button>
      <textarea class="prompt-textarea" id="pt-${d}" style="display:none"
        oninput="updatePromptPreview()">${DEFAULT_PROMPTS[d] || ''}</textarea>
    </div>
  `).join('');
}

function togglePromptExpand(d) {
  const ta = document.getElementById(`pt-${d}`);
  const btn = ta.previousElementSibling;
  if (ta.style.display === 'none') {
    ta.style.display = 'block'; btn.textContent = '收起 ▴';
  } else {
    ta.style.display = 'none'; btn.textContent = '展开编辑 ▾';
  }
}

function getConfig() {
  const dims = [...document.querySelectorAll('.dim-tag.on')].map(t => t.dataset.d);
  const prompts = {};
  dims.forEach(d => {
    const ta = document.getElementById(`pt-${d}`);
    prompts[d] = ta ? ta.value : DEFAULT_PROMPTS[d] || '';
  });
  const depth = document.querySelector('input[name=depth]:checked')?.value || 'standard';
  const language = document.querySelector('input[name=language]:checked')?.value || 'zh';
  const extra = document.getElementById('extra-instructions').value.trim() || null;
  return { dims, prompts, depth, language, extra };
}

function updatePromptPreview() {
  const { dims, prompts, depth, language, extra } = getConfig();
  const depthDesc = {light:'brief (1-2 items max)', standard:'thorough (2-4 items)', deep:'exhaustive'}[depth];
  const langDesc = {zh:'Chinese (中文)', en:'English', bilingual:'bilingual'}[language];
  const dimSection = dims.map(d => `[${d.toUpperCase()}] ${prompts[d] || ''}`).join('\n');
  const extraSection = extra ? `\nExtra: ${extra}` : '';
  const preview = `[SYSTEM]\nYou are an expert literary annotator.\nDepth: ${depthDesc}.\nLanguage: ${langDesc}.\n\n${dimSection}${extraSection}\n\nReturn JSON: {"vocab":[...],"grammar":[...],...}`;
  document.getElementById('prompt-preview').textContent = preview;
}

function renderParagraphs() {
  const container = document.getElementById('paragraphs-container');
  let html = '';
  let lastChapter = null;
  for (const p of paragraphs) {
    if (p.chapter_num !== lastChapter) {
      html += `<div class="chapter-divider">${p.chapter_title}</div>`;
      lastChapter = p.chapter_num;
    }
    const anns = annotations[p.id] || [];
    html += `
      <div class="para-block" id="pb-${p.id}" onclick="selectPara(${p.id})">
        <div class="para-meta">Ch.${p.chapter_num} · §${p.section_num}</div>
        <div class="para-text">${escHtml(p.text_en)}</div>
      </div>
      <div class="ann-cards" id="ac-${p.id}">
        ${anns.map(annCard).join('')}
      </div>`;
  }
  container.innerHTML = html;
}

function annCard(a) {
  return `<div class="ann-card" data-dim="${a.dimension}">
    <div class="ann-card-term">${escHtml(a.term)}</div>
    <div class="ann-card-body">${escHtml(a.body_markdown)}</div>
  </div>`;
}

function selectPara(id) {
  document.querySelectorAll('.para-block').forEach(b => b.classList.remove('active'));
  const el = document.getElementById(`pb-${id}`);
  if (el) el.classList.add('active');
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function startAnnotation() {
  const btn = document.getElementById('btn-annotate');
  if (btn.disabled) return;
  const { dims, prompts, depth, language, extra } = getConfig();
  if (!dims.length) { alert('请至少选择一个标注维度'); return; }
  if (!scopeChapterNums.size) { alert('请至少选择一个章节'); return; }

  btn.disabled = true;
  btn.textContent = '正在标注…';

  const r = await fetch('/api/admin/jobs', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      book_id: BOOK_ID,
      scope_chapter_nums: [...scopeChapterNums],
      dimensions: dims,
      prompts,
      depth, language,
      extra_instructions: extra,
    })
  });
  if (!r.ok) {
    alert('启动失败: ' + await r.text());
    btn.disabled = false; btn.textContent = '开始标注';
    return;
  }
  const { job_id } = await r.json();

  const es = new EventSource(`/api/admin/jobs/${job_id}/stream`);
  es.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'annotation') {
      const container = document.getElementById(`ac-${ev.paragraph_id}`);
      if (container) {
        const card = document.createElement('div');
        card.className = 'ann-card';
        card.dataset.dim = ev.dimension;
        card.innerHTML = `<div class="ann-card-term">${escHtml(ev.term)}</div>
          <div class="ann-card-body">${escHtml(ev.body_markdown)}</div>`;
        container.appendChild(card);
        const pb = document.getElementById(`pb-${ev.paragraph_id}`);
        if (pb) pb.scrollIntoView({behavior:'smooth', block:'nearest'});
      }
    } else if (ev.type === 'done' || ev.type === 'error') {
      es.close();
      btn.disabled = false;
      btn.textContent = '重新标注';
      if (ev.type === 'error') alert('标注出错: ' + ev.message);
    }
  };
  es.onerror = () => {
    es.close();
    btn.disabled = false; btn.textContent = '重新标注';
  };
}
</script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add admin/edit/index.html admin/edit/styles.css
git commit -m "feat: add admin annotation editor (two-pane, SSE live annotations)"
```

---

### Task 11: nginx config — serve /admin/ as static files

**Files:**
- Modify: `deploy/nginx-belowiceberg.conf`

- [ ] **Step 1: Update nginx config**

Replace the current `/admin` block:

```nginx
    location /admin {
        proxy_pass http://127.0.0.1:8001;
        ...
    }
```

With two static-file location blocks:

```nginx
    location /admin/ {
        try_files $uri $uri/index.html =404;
    }
```

The `/api/admin/` routes are already handled by the `/api/` block above it. The old proxy block must be removed entirely.

Final `deploy/nginx-belowiceberg.conf`:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    root /var/www/belowiceberg;
    index index.html;

    location /static/ {
        alias /opt/belowiceberg/static/;
        access_log off;
        expires 1h;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    location /admin/ {
        try_files $uri $uri/index.html =404;
    }

    location = /gatsby { try_files /gatsby.html =404; }

    location / { try_files $uri $uri/ =404; }
}
```

Note: `proxy_read_timeout` increased to `300s` (from 120s) to allow long annotation jobs to stream without nginx cutting the connection.

- [ ] **Step 2: Commit**

```bash
git add deploy/nginx-belowiceberg.conf
git commit -m "fix: serve /admin/ as static files, increase proxy_read_timeout to 300s for SSE"
```

---

### Task 12: Deploy to Vultr

**Server:** 66.135.16.106 · `/var/www/belowiceberg/` · service `belowiceberg-api`

- [ ] **Step 1: Push to GitHub**

```bash
cd /Users/ben/Downloads/belowiceberg
git push origin main
```

- [ ] **Step 2: SSH and deploy**

```bash
ssh root@66.135.16.106
```

On server:

```bash
cd /var/www/belowiceberg && git pull origin main
```

- [ ] **Step 3: Install new Python deps on server**

```bash
cd /opt/belowiceberg
source venv/bin/activate
pip install ebooklib==0.18.* beautifulsoup4==4.12.* lxml
```

- [ ] **Step 4: Run DB migration**

The migration runs automatically on app startup via `migrate()`. But verify it:

```bash
source /etc/belowiceberg/admin.env
python -c "
import sys; sys.path.insert(0, '/opt/belowiceberg')
from app.db import migrate, get_conn
migrate()
v = get_conn().execute('SELECT version FROM schema_version').fetchone()[0]
print('schema_version =', v)
assert v == 2
"
```

Expected: `schema_version = 2`

- [ ] **Step 5: Seed Gatsby**

```bash
source /etc/belowiceberg/admin.env
python /var/www/belowiceberg/server/scripts/seed_gatsby.py \
  /var/www/belowiceberg/gatsby-teaching-edition.html
```

Expected: `Done. book_id=1`, `Total paragraphs seeded: 400+`

- [ ] **Step 6: Restart service**

```bash
systemctl restart belowiceberg-api
systemctl status belowiceberg-api
```

Expected: `active (running)`

- [ ] **Step 7: Reload nginx config**

```bash
nginx -t && systemctl reload nginx
```

Expected: `syntax is ok` + `configuration file ... test is successful`

---

### Task 13: E2E smoke test

Manual browser checks after deploy.

- [ ] **Check 1: Admin dashboard loads**

Navigate to `http://66.135.16.106/admin/`. Without login → should redirect to `/login/?next=/admin/`.

- [ ] **Check 2: Login and reach admin**

Login as `admin@gmail.com / admin123`. After login, navigate to `/admin/`. Should see "管理后台" + "了不起的盖茨比" in the book list with chapter count and paragraph progress.

- [ ] **Check 3: Admin dashboard — status toggle**

Click the DRAFT badge on The Great Gatsby → should toggle to PUBLISHED. Click again → back to DRAFT.

- [ ] **Check 4: Annotation editor loads**

Click "标注" button on Gatsby → navigates to `/admin/edit/?book=1`. Should see left pane with paragraph text and right pane with scope/dimensions config.

- [ ] **Check 5: Scope selector**

Right pane scope list should show 9 chapters. Uncheck Chapter 1. "整本书" toggle re-checks all. Works.

- [ ] **Check 6: Dimension tags**

Click vocab tag → deselects (dims out). Click again → reselects. Prompt preview updates when dimensions change.

- [ ] **Check 7: Start annotation**

Select only Chapter 1. Select only "vocab". Click "开始标注". Button becomes disabled + "正在标注…". After a few seconds, annotation cards appear in the left pane under paragraph text. On completion, button becomes "重新标注".

- [ ] **Check 8: Non-admin user blocked**

Log out. Navigate to `/api/admin/books` → should return 401.

- [ ] **Check 9: API books endpoint**

```bash
curl -s http://66.135.16.106/api/admin/books
```

Expected: `{"detail":"login required"}` (401)

- [ ] **Step 10: Commit smoke test passed**

```bash
git tag v0.3.0-plan-b
git push origin main --tags
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| 6 new tables with correct schema | Task 1 |
| books.py CRUD + annotation queries | Task 2 |
| call_once() for non-streaming DeepSeek | Task 3 |
| Background runner, pre-pass, per-paragraph | Task 4 |
| Admin book CRUD routes (list/patch/delete/chapters/paragraphs/annotations) | Task 5 |
| Admin jobs routes + SSE stream | Task 6 |
| EPUB parser (ebooklib + bs4) | Task 7 |
| Gatsby seed from HTML | Task 8 |
| Admin dashboard (header, upload, filter, book list, status toggle) | Task 9 |
| Annotation editor (two-pane, scope, dims+prompts, depth/lang, extra, preview, SSE) | Task 10 |
| nginx: /admin/ static, /api/ proxy, 300s timeout | Task 11 |
| Deploy + Gatsby seed on server | Task 12 |
| E2E smoke test 9 checks | Task 13 |

All spec requirements covered. No placeholders. Type names consistent across tasks (`book_id`, `chapter_num`, `section_num`, `para_num`, `prompt_version_hash`).
