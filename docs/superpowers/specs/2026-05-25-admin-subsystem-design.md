# BelowIceberg Admin Subsystem — Design Spec

**Date:** 2026-05-26
**Author:** brainstorming session (Claude + ben)
**Depends on:** `2026-05-25-prototype-shipping-design.md` (Plan A ships 1-4 already live)

## Goal

Build the admin subsystem: a book management dashboard, a two-pane annotation editor, and a background annotation job runner powered by DeepSeek V3. No architecture changes — FastAPI + SQLite + static HTML + Babel-React-in-browser.

---

## Scope: 3 components

| Component | Route | Status |
|---|---|---|
| Admin dashboard | `/admin/` | New |
| Annotation editor | `/admin/edit` | New |
| Annotation runner | (background + SSE) | New |

---

## Data Model

All new tables. Existing tables (`users`, `sessions`) are untouched.

```sql
-- Books in the catalog
CREATE TABLE books (
    id          INTEGER PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,          -- e.g. "great-gatsby"
    title_en    TEXT NOT NULL,
    title_zh    TEXT NOT NULL,
    author      TEXT NOT NULL,
    cover_css   TEXT,                          -- inline CSS for gradient cover art
    status      TEXT NOT NULL DEFAULT 'draft', -- 'draft' | 'published'
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Chapters within a book
CREATE TABLE chapters (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER NOT NULL REFERENCES books(id),
    chapter_num INTEGER NOT NULL,
    title_zh    TEXT NOT NULL,
    text_full   TEXT NOT NULL,                 -- full English source text
    UNIQUE(book_id, chapter_num)
);

-- Sections within a chapter (e.g. "§1", "§2")
CREATE TABLE sections (
    id          INTEGER PRIMARY KEY,
    chapter_id  INTEGER NOT NULL REFERENCES chapters(id),
    section_num INTEGER NOT NULL,
    title_zh    TEXT,
    UNIQUE(chapter_id, section_num)
);

-- Paragraphs within a section
CREATE TABLE paragraphs (
    id               INTEGER PRIMARY KEY,
    section_id       INTEGER NOT NULL REFERENCES sections(id),
    para_num         INTEGER NOT NULL,
    text_en          TEXT NOT NULL,
    worth_annotating INTEGER NOT NULL DEFAULT 1, -- 0 = skip (pre-pass filtered)
    UNIQUE(section_id, para_num)
);

-- Generated annotation cards
CREATE TABLE annotations (
    id                  INTEGER PRIMARY KEY,
    paragraph_id        INTEGER NOT NULL REFERENCES paragraphs(id),
    dimension           TEXT NOT NULL,           -- 'vocab'|'grammar'|'syntax'|'lit'|'cult'|'style'
    term                TEXT NOT NULL,
    body_markdown       TEXT NOT NULL,
    prompt_version_hash TEXT NOT NULL,
    model               TEXT NOT NULL DEFAULT 'deepseek-chat',
    generated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(paragraph_id, dimension, term)
);

-- Annotation jobs (one per run, persisted for resumability)
CREATE TABLE annotation_jobs (
    id               INTEGER PRIMARY KEY,
    book_id          INTEGER NOT NULL REFERENCES books(id),
    scope_json       TEXT NOT NULL,             -- JSON array of chapter_ids in scope
    dimensions_csv   TEXT NOT NULL,             -- e.g. "vocab,grammar,syntax"
    prompts_json     TEXT NOT NULL,             -- JSON object: {dimension: prompt_text}
    depth            TEXT NOT NULL DEFAULT 'standard', -- 'light'|'standard'|'deep'
    language         TEXT NOT NULL DEFAULT 'zh', -- 'zh'|'en'|'bilingual'
    extra_instructions TEXT,
    prompt_version_hash TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'running'|'done'|'error'
    progress_done    INTEGER NOT NULL DEFAULT 0,
    progress_total   INTEGER NOT NULL DEFAULT 0,
    error_message    TEXT,
    started_at       TEXT,
    completed_at     TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**Key design decisions:**
- `sections` table is explicit (chapter → section → paragraph), matching the Gatsby reader's hierarchy.
- `annotations` has a unique constraint on `(paragraph_id, dimension, term)` for idempotency. Re-running a job with the same config skips existing annotations.
- `prompt_version_hash` is SHA-256 of the assembled prompt (system prompt + dimension prompts + depth + language + extra). Changing any config produces a new hash and triggers re-generation.
- `worth_annotating` flag is set by the pre-pass filter before the main annotation loop.

---

## Page 7: Admin Dashboard (`/admin/`)

**Access control:** requires `is_admin=true` on session user. Non-admins → 403 page.

**Layout (top to bottom):**

1. **Header row:** "管理后台" h1 + gray `ADMIN` badge + `+ 上传新书` primary gold button (right-aligned).

2. **Upload zone** (hidden by default, toggled by header button):
   - Full-width drag-drop target with dashed border.
   - Accepts `.epub` files.
   - On drop/select: POST to `/api/admin/books/upload` (multipart). Server parses EPUB synchronously (FastAPI + ebooklib), creates book + chapters + sections + paragraphs rows, returns book id.
   - Shows progress spinner during upload/parse. On success: hides zone, refreshes book list, opens editor for new book.
   - On error: shows inline error message.

3. **Filter row:** book count + filter pills `全部 | 草稿 | 已发布`. Active pill gold-filled, inactive outlined.

4. **Book list:** one row per book.
   - Mini cover thumbnail (40×54px gradient or art, same `cover_css` as catalog).
   - Title (English + Chinese).
   - Author.
   - Chapter count.
   - Annotation progress: "N / M 段已标注" (annotated paragraphs / total paragraphs).
   - Status badge: `DRAFT` (gray) or `PUBLISHED` (gold).
   - Actions: `预览` button (opens reader in new tab) + `标注` button (opens editor).

**Status simplification:** two states only — `DRAFT` and `PUBLISHED`. No intermediate state. Annotation progress is informational text, not a status.

**Publish/unpublish:** clicking the status badge toggles `draft ↔ published` via `PATCH /api/admin/books/{id}` with `{"status": "published"|"draft"}`.

---

## Page 8: Annotation Editor (`/admin/edit?book={id}`)

**Two-pane layout** (left: 55%, right: 45%, min-height: 100vh).

### Left pane — text preview

Styled identically to the Gatsby reader. Shows the book's text with annotation cards inline.

- **Header:** `← 返回` link (→ /admin/) + book title (English + Chinese).
- **Primary action button** (top-right of header): "开始标注" (idle) → "正在标注…" (running, disabled). Single button, no separate save/submit.
- **Paragraph rendering:** each paragraph is clickable (`selectPara()`). Clicking highlights it and scrolls the right pane to the relevant scope entry.
- **Annotation cards** appear inline beneath each paragraph. Cards use the existing Gatsby reader card style. Dimensions shown as colored pills.
- **Chapter navigation:** controlled by the scope selector in the right pane (clicking a chapter in the scope list scrolls the left pane to that chapter).

No chapter tab row in the left pane — navigation is driven from the right pane scope list.

### Right pane — annotation config

Scrollable. Five sections top to bottom, separated by hairlines.

**Section 1 — Scope**

Header: "SCOPE · 标注范围"

List of all chapters in the book. Each row:
- Checkbox (checked = in scope).
- Chapter title (e.g. "第一章 · 贵格兰特的派对").
- Progress: "N/M" (annotated/total paragraphs in chapter).

Footer row: "整本书 · 全部章节" shortcut — checks/unchecks all at once.

**Section 2 — Dimensions**

Header: "DIMENSIONS · 标注维度"

Six checkable tags in a wrap row:
- `词汇` (--vocab blue), `语法` (--gram green), `句法` (--syntax purple), `文学手法` (--lit red), `文化背景` (--cult teal), `风格分析` (--style-c olive)

Each checked dimension reveals a prompt editor below it:
- Label: dimension name + "提示词".
- Textarea with default prompt preloaded (see defaults below).
- "展开编辑 ▾" toggle collapses/expands the textarea.

Default prompts (English, sent to DeepSeek):
- **vocab:** "Identify vocabulary worth teaching: unusual words, literary diction, words used in unexpected ways. For each, write a 2-3 sentence explanation in the target language."
- **grammar:** "Identify grammatical structures worth teaching: tenses, passive voice, complex clauses, subject-verb agreement. Explain the structure and why it matters here."
- **syntax:** "Identify syntactic patterns worth teaching: sentence length, inversion, parallelism, fragmentation. Explain the effect."
- **lit:** "Identify literary devices: metaphor, simile, irony, foreshadowing, allusion. Explain the device and its effect in context."
- **cult:** "Identify cultural references: historical events, geography, social customs, period details. Explain what a non-Western reader needs to know."
- **style:** "Identify stylistic choices: register, tone, rhythm, word choice. Explain what they reveal about the narrator or characters."

**Section 3 — Depth & Language**

Header: "SETTINGS · 深度与语言"

Two radio rows:
- **Depth:** `简读` (light) · `标准` (standard, default) · `深度` (deep)
- **Language:** `中文` (default) · `English` · `双语`

**Section 4 — Extra Instructions**

Header: "EXTRA · 补充指令"

Textarea: "Any other guidance appended to every prompt". Placeholder: "例如：重点关注比喻和讽刺手法…"

**Section 5 — Prompt Preview**

Header: "PREVIEW · 提示词预览"

Read-only `<pre>` block showing the assembled final prompt that will be sent to DeepSeek for the first paragraph in scope. Updates live as config changes.

Format:
```
[SYSTEM]
You are an expert literary annotator for Chinese readers learning English literature.
<book context>
<dimension prompts for enabled dimensions>
Depth: {depth}. Language: {language}.

[USER]
Paragraph:
"{paragraph text}"

Return JSON: {"vocab": [...], "grammar": [...], ...}
```

**Primary action button behavior:**

- Clicking "开始标注" POSTs to `POST /api/admin/jobs` with full config JSON, then immediately opens SSE stream on `GET /api/admin/jobs/{id}/stream`.
- Left pane shows annotation cards appearing in real time as SSE events arrive.
- Button label changes to "正在标注…" and becomes disabled.
- When stream ends (job done or error), button resets to "开始标注" (or "重新标注" if some annotations already exist).
- No locked UI — user can scroll, select paragraphs, and edit config in the right pane while job runs (config changes don't affect the running job; they affect the next run).

---

## Annotation Runner (Backend)

### API Routes

```
POST   /api/admin/books/upload           multipart EPUB upload + parse
GET    /api/admin/books                  list all books with annotation progress
PATCH  /api/admin/books/{id}             update status (draft/published)
DELETE /api/admin/books/{id}             delete book + cascade

GET    /api/admin/books/{id}/chapters    list chapters with section/paragraph counts
GET    /api/admin/books/{id}/paragraphs  all paragraphs (for editor left pane)
GET    /api/admin/books/{id}/annotations all annotations (for editor left pane)

POST   /api/admin/jobs                   create + enqueue annotation job
GET    /api/admin/jobs/{id}              job status
GET    /api/admin/jobs/{id}/stream       SSE stream of annotation events
DELETE /api/admin/jobs/{id}              cancel running job
```

All `/api/admin/*` routes require `is_admin=true`. Return 403 otherwise.

### Job Lifecycle

1. POST `/api/admin/jobs` → creates `annotation_jobs` row (status=pending), returns `{job_id}`.
2. Background asyncio worker picks up the job. Single-job lock (`asyncio.Lock`) — one job at a time.
3. Worker:
   a. **Pre-pass filter** (1 call per chapter in scope): ask DeepSeek which paragraphs are worth annotating. Sets `paragraphs.worth_annotating = 0` for trivial paragraphs (dialog tags, one-word lines, etc.). 1 call per chapter ≈ 9 calls for full Gatsby.
   b. **Chapter overview** (1 call per chapter): ask DeepSeek for a brief chapter-level annotation (themes, major devices). Stored as a special annotation with `dimension='overview'`. 1 call per chapter ≈ 9 calls.
   c. **Per-paragraph main pass**: for each `worth_annotating=1` paragraph in scope, one DeepSeek call returning multi-dimension JSON. Skip if annotation row already exists with same `prompt_version_hash` (idempotency). ≈ 216 calls for full Gatsby.
4. Each completed annotation → INSERT into `annotations` → send SSE event to connected clients.
5. On completion: update job status=done, completed_at.
6. On error: update status=error, error_message. Client SSE stream receives error event.

### DeepSeek Call Shape

**Pre-pass filter call (per chapter):**
```
System: You are filtering paragraphs in a literary text. Return a JSON array of paragraph IDs worth annotating. Skip: dialog tags ("he said"), single sentences with no literary content, repeated phrases, chapter headings.
User: [list of {id, text} for all paragraphs in chapter]
Response: [42, 45, 47, ...]
```

**Chapter overview call:**
```
System: Briefly annotate this chapter for Chinese students of English literature. Return JSON: {"themes": "...", "devices": "...", "summary_zh": "..."}.
User: [chapter title + first 500 chars of text]
```

**Per-paragraph main pass call:**
```
System: You are an expert literary annotator...
[dimension prompts for enabled dimensions]
Depth: standard. Language: 中文.
Return JSON: {"vocab": [{"term": "...", "body_markdown": "..."}], "grammar": [...], ...}
Only include dimensions with findings. Empty array if nothing to annotate for a dimension.

User: Paragraph: "[paragraph text]"
```

**Model:** `deepseek-chat` (DeepSeek V3). Temperature 0.3 for consistency.

**Prompt caching:** The system prompt (including all dimension prompts) is identical for all paragraphs in a single job run. DeepSeek's prompt cache will cache it after the first call, reducing cost by ~75% on subsequent calls.

### SSE Event Format

```
data: {"type": "progress", "done": 12, "total": 234}
data: {"type": "annotation", "paragraph_id": 42, "dimension": "vocab", "term": "verdant", "body_markdown": "..."}
data: {"type": "done", "job_id": 7}
data: {"type": "error", "message": "DeepSeek API rate limit"}
```

### Resumability

If the server restarts mid-job:
- On startup, check for any `annotation_jobs` row with `status='running'` → reset to `status='pending'`.
- Worker picks it up on next run.
- Idempotency key `(paragraph_id, dimension, term)` prevents duplicate annotations.

---

## EPUB Parsing

Use `ebooklib` + `BeautifulSoup4` (both installable via pip, no system deps).

Parse flow:
1. Read EPUB → extract chapters in spine order.
2. Each chapter: strip HTML tags, split into sections by `<h2>`/`<h3>` or `§` markers.
3. Each section: split into paragraphs by `<p>` tags or double newlines.
4. Store in `chapters` → `sections` → `paragraphs` tables.

**Fallback:** if no section markers found, create one section per chapter (section_num=1, title_zh=NULL).

For The Great Gatsby (already live): data is seeded manually from the existing hardcoded text in `gatsby-teaching-edition.html` rather than EPUB upload. A seed script populates the database tables directly.

---

## Shipping Order (Plan B)

1. **Data model migration** — create all 6 new tables. Seed Gatsby chapters/sections/paragraphs from existing hardcoded text.
2. **Admin dashboard** — frontend + backend book CRUD + admin gating.
3. **EPUB upload + parse** — multipart endpoint, ebooklib parser.
4. **Annotation editor (left pane)** — text rendering + annotation cards from DB.
5. **Annotation editor (right pane)** — scope/dimensions/depth/language/extra/preview config UI.
6. **Annotation runner** — background worker + DeepSeek calls + idempotency.
7. **SSE streaming** — wire editor primary button to runner, show live annotation cards.
8. **Publish/unpublish flow** — status toggle propagates to `/books/` catalog and Gatsby reader.

---

## Open Questions (resolved)

- **Want-to-read list source:** hardcoded in `library/index.html` for now (already shipped in Plan A). No DB table needed yet.
- **Auto-publish toggle:** deferred. Admin manually toggles draft → published via dashboard status badge.
- **Gatsby seed data:** manual seed script from existing hardcoded text, not EPUB upload. EPUB upload path is for new books.

---

## Out of Scope

- Multi-user annotation (single admin only).
- Annotation review/approval workflow.
- EPUB DRM handling.
- DeepSeek streaming token-by-token (full paragraph response arrives at once; SSE sends completed annotations, not mid-generation tokens).
- Note-taking by readers (existing `/api/notes` unchanged).
