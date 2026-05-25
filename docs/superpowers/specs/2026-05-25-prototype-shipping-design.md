# BelowIceberg Prototype Shipping — Design Spec

**Date:** 2026-05-25
**Author:** brainstorming session (Claude + ben)
**Source:** `belowiceberg-prototype.html` (2743-line standalone prototype, 8 pages)

## Goal

Polish the live BelowIceberg site by shipping the prototype's interaction patterns to the deployed pages, page by page. Each ship is its own commit + deploy + smoke test. **No architecture changes** — keep FastAPI + SQLite + static HTML + Babel-React-in-browser.

The user explicitly wants the homepage to keep its current look. Other pages get targeted polish based on what was reviewed piece-by-piece in the prototype.

---

## Scope: 8 Pages

| # | Path | Status today | Action |
|---|---|---|---|
| 1 | `/` | live | **Targeted tweaks** (4 specific changes) |
| 2 | `/books/` | live (skeleton) | **New full catalog page** |
| 3 | `/login/` | live | **No change** |
| 4 | `/library/` | live (skeleton) | **Redesign** |
| 5 | `/settings/` | live | **No change** |
| 6 | `/gatsby` | live | **Navbar polish** (login state + zone layout) |
| 7 | `/admin/` | new | **Build dashboard** |
| 8 | `/admin/edit` | new | **Build annotation editor** |

---

## Design Tokens (locked from prototype)

These match the existing live site and the gatsby reader. Do not change.

**Colors:**
- `--bg #fafaf7` · `--bg2 #f2efe7` · `--bg3 #e8e4d8` · `--bg4 #ded9cb`
- `--gold #b8942e` · `--gold-pale rgba(184,148,46,0.08)` · `--gold-dim rgba(184,148,46,0.4)`
- `--text #2d2a20` · `--text2 #6b5e3e` · `--text3 #a89870` · `--ink #1a1a15`
- Dimension colors: `--vocab #3a7bb5` (词汇), `--gram #3a8b5e` (语法), `--syntax #7a4f9b` (句法), `--lit #c45a3a` (文学), `--cult #3a7a8b` (文化), `--style-c #7a7a3a` (风格)
- `--border rgba(184,148,46,0.25)` · `--r 8px`

**Fonts:** Playfair Display (headings, English), Lora (body), Noto Serif SC (Chinese), JetBrains Mono (eyebrows, labels, mono).

**Hairlines:** `0.5px solid var(--border)` everywhere.

---

## Page-by-page Specs

### 1. Home (`/` — `belowiceberg-website-v2.html`)

**Four targeted changes only. Layout, hero, method, reader sample, manifesto, footer stay identical.**

**1a. Nav — add login state**

Current nav has: logo + 4 links (方法论 / 书目 / 试读 / 关于B社) + 开始阅读 CTA.

Add login-aware right-side:
- **Guest:** insert `<a href="/login" class="nav-login">登录</a>` between nav-links and nav-cta. Outlined pill (`0.5px solid var(--border)`, transparent bg, gold hover border).
- **Logged in:** replace 开始阅读 CTA with two elements — `<a href="/library" class="nav-shelf">我的书房</a>` + user chip (`<a href="/settings" class="nav-user-chip">` with circular gold avatar showing display-name initial + display name + ▾ caret).

Detection: the existing settings page already calls `/api/me`. Reuse the same fetch on the home page. Inline a small script that hides/shows the right nodes based on the response. Failure mode (network error, 401) defaults to guest.

**1b. Hero CTAs — change targets**

Current:
```html
<a href="#sample" class="btn-primary">免费试读</a>
<a href="#books" class="btn-secondary">浏览全部书目</a>
```

Change to:
```html
<a href="/gatsby" class="btn-primary">免费试读</a>
<a href="/books" class="btn-secondary">浏览全部书目</a>
```

Old behavior scrolled to in-page anchors; new behavior navigates to the actual reader and the full catalog page.

**1c. Books section — add catalog link**

After the existing 4-book grid (`.books-grid` inside `<section class="section" id="books">`), append:

```html
<div class="books-cta">
  <a href="/books">查看完整书库 →</a>
</div>
```

Style: centered, outlined pill matching `.btn-secondary`. The existing 4-book "现有书目" grid stays unchanged.

**1d. Nav link "书目" — keep as anchor**

`#books` anchor stays for the in-page section. The new "查看完整书库" CTA inside the section is the explicit route to `/books`.

---

### 2. Books catalog (`/books/`)

**New full catalog page.** Replaces whatever placeholder is at that route.

Structure:
- Page header: section-tag "COLLECTION · 全部书库" + h1 "经典文学精读" + subtitle.
- Search bar: filter by title/author/Chinese title/keywords (`data-search` attribute on each card).
- Filter tabs: 全部 / 已上线 / 即将推出 (toggles `data-status` filter).
- Book grid: same `.book-card` markup as homepage, full set. Live books navigate to their reader; soon books show a "制作中" toast on click.
- Empty state: when no matches, show "没有找到匹配的书籍".

Data source: hardcoded book list in the HTML for now (no admin-driven catalog yet). Will switch to `/api/books` once admin upload flow is built.

---

### 3. Login (`/login/`) — no change

Already deployed split-layout variant B. Skip.

---

### 4. Library (`/library/`) — redesign

Drop the current skeleton (continue-reading card + stats row + tiny book list + notes). Replace with:

**4a. Tabs (3 only):**
- `正在阅读 <count>` (active)
- `想读 <count>`
- `已读完 <count>`

No "收藏的注解" tab. Pill group with rounded outer corners; active tab gold fill, inactive ones outlined.

**4b. "正在阅读" tab content:**

Section eyebrow "CURRENTLY READING · 正在阅读" + uniform 4-column tall cover-card grid (auto-fill, minmax(200px, 1fr)).

Each card:
- Tall 3:4 cover (gradient or art) with title in English + Chinese inside.
- Bottom 1/3 of cover: progress overlay (rgba white + blur), showing "第 N 章 · 第 M 节" + gold progress bar + "Ch.N · M/T" left + "XX%" right.
- Below card: English title + Chinese title + author meta.

**4c. "想读" tab content:**

Section header: `WANT TO READ · 想读  B社系列下一批书目` + right-aligned count "N 部即将上架".

Grid of upcoming book covers (no progress overlay, just "即将上架" badge at cover bottom).

**4d. Data source:**

Reuse existing `/api/library` for in-progress books. Add `/api/want-to-read` (or read from a hardcoded admin-managed list — TBD in implementation plan).

No stats row. No suggest card. No notes section.

---

### 5. Settings (`/settings/`) — no change

User confirmed live page is good. Skip.

---

### 6. Reader (`/gatsby`) — navbar polish

Current navbar has brand + chapter tabs + book/library buttons. Replace with **3-zone grid layout**:

**Left zone:**
- `← 书库` text link (back to /books)
- BelowIceberg brand label

**Center zone:**
- Chapter tabs (Ch.1 active gold, locked future chapters dimmed)

**Right zone (2 states):**
- **Logged in:** `我的书房` link (→ /library) + user chip (avatar + display name + ▾, → /settings dropdown).
- **Logged out:** Single gold pill "登录" button. Link includes `?next=/gatsby` so login returns to reading position.

Rename "书架" to **"我的书房"** everywhere it appears in reader UI.

All other reader content (cover page, chapter heading, section header, original text styling, annotation cards) is already correct in the live deploy. No changes there.

---

### 7. Admin dashboard (`/admin/`) — new

Header: "管理后台" + ADMIN badge + "+ 上传新书" primary button.

Hidden upload zone (toggled by button): drag-drop EPUB target with progress bar during parsing.

Book filter row: count + filter pills (全部 / 草稿 / 已发布).

Book list: rows with mini cover + title + author + chapter count + N/M annotated + status badge + actions (预览 / 编辑 or 开始标注).

**Status simplification — only 2 states:**
- `DRAFT` (gray)
- `PUBLISHED` (gold)

Drop the prototype's "ANNOTATING" intermediate state. A book is either still being worked on (draft) or live for readers (published). Annotation progress shows as "N/M annotated" text, not a separate status.

Admin gating: route requires `is_admin=true` on the session user. Non-admins get 403.

---

### 8. Admin annotation editor (`/admin/edit`) — new

**Two-pane layout:**

**Left pane — text preview** (same visual style as Gatsby reader):
- Header: `← 返回` + book title + single primary action button (no separate 保存草稿 + 提交审核 — merged into one "保存" with auto-publish toggle in the right pane).
- Chapter switcher merged into the **scope selector** on the right (not a separate top-of-pane tab row).
- Paragraphs with `selectPara()` click-to-annotate.
- Existing annotation cards shown inline beneath the active paragraph as they are generated.

**Right pane — annotation config (top to bottom):**

1. **Scope** — list of chapters (each with check + chapter title + "N/M" progress) + "整本书 · 全部章节" at bottom. Selecting a scope sets the AI annotation target.

2. **Dimensions** — 6 checkable tags (词汇/语法/句法/文学手法/文化背景/风格分析) colored with dimension tokens. Each enabled dimension reveals a per-dimension prompt editor (textarea, "展开编辑 ▾" toggle, default prompt preloaded).

3. **Depth & language** — sliders or radio rows for analysis depth (light/standard/deep) and explanation language (中文/英文/双语).

4. **Extra instructions** — free-form textarea for "any other guidance" appended to the prompt.

5. **Prompt preview** — read-only block showing the composed final prompt that will be sent to DeepSeek.

**Cut from prototype:** method selector (always AI auto), separate locked "annotation running" UI.

**Annotation running behavior:** No special locked state. Clicking the primary action triggers streaming generation; new annotation cards appear inline beneath paragraphs as they stream in. The user can keep navigating the editor while it runs.

---

## Shipping Order

Smallest first, each independently deployable:

1. **Home page tweaks** (`/`) — 4 small edits to existing HTML. ~30 min.
2. **Books catalog** (`/books/`) — new self-contained page. ~1 hr.
3. **Library redesign** (`/library/`) — frontend rewrite, existing API. ~2 hr.
4. **Reader navbar polish** (`/gatsby`) — HTML/CSS in reader file. ~1 hr.
5. **Admin dashboard** (`/admin/`) — new backend (book CRUD + upload) + new frontend. ~half day.
6. **Admin editor** (`/admin/edit`) — new backend (annotation jobs + DeepSeek streaming integration if not already done) + new frontend two-pane editor. ~full day.

Each ship: commit → deploy via existing rsync/restart pipeline → smoke test in browser → next.

---

## Open Questions

- **Want-to-read list source:** hardcoded JSON, admin-managed table, or pull from books-catalog "soon" status? → resolve in implementation plan.
- **Auto-publish toggle on editor save:** include in v1 of admin editor or defer? → resolve in implementation plan.
- **Mobile breakpoints:** every page must work on phone (per user's memory feedback "minimal + always responsive"). Each plan task includes a mobile check step.

---

## Out of Scope

- New auth providers (OAuth Apple/Google buttons stay disabled).
- Token/credit system (settings shows balance but recharge is disabled).
- Notes/highlights system (existing `/api/notes` keeps current behavior).
- EPUB parsing internals (assume an existing EPUB → chapter+paragraph parser; if missing, scope adds in admin task).
- Internationalization beyond zh-CN/en (the site is Chinese-first and stays that way).
