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

UPDATE schema_version SET version = 2;
