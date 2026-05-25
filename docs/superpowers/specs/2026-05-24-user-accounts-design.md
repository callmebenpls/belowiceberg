# User Accounts & Logged-in Reading — Design Spec

**Date:** 2026-05-24
**Status:** Approved for planning
**Project:** belowiceberg

## Problem

Today the site is fully public read + admin-only annotation authoring. The product wants per-user state: real signups, per-user AI annotations, reading progress, a personal "书房" (library), and a settings page. This spec covers all of the above as one connected slice — auth + per-user data, no payments or tokens.

## Goal

Anyone can sign up with email + password. Logged-in readers get:
- An AI selection bar on book pages that saves annotations to *their* private store (not public).
- Reading-progress tracking that surfaces in the library as "continue where you left off."
- A library page listing their AI notes across all books and recent reading position.
- A settings page where they can edit display name, change password, clear reading progress, sign out.

The admin (you) keeps the existing ability to author public annotation cards.

## Non-goals (deferred)

- Payments / tokens / book entitlements
- OAuth (Apple / Google)
- Email service (password reset, signup confirmation, editor dispatch)
- Bookmarks (starring other people's annotation cards into a library)
- Public discussion / community-edited notes
- EPUB export wiring

## Scope decisions captured from brainstorm

| Decision | Value |
|---|---|
| Auth | Email + password (bcrypt) + signed session cookie |
| Password reset | None in v1 — admin manually resets via CLI |
| Content gating | None — all books readable anonymously |
| Login-gated features | AI selection bar, library, settings |
| User annotation visibility | Private to the user (separate from admin public sidecar) |
| Annotation badge | None — saved notes look like any other card |
| Bookmarks | Dropped from v1 |
| Reading-progress granularity | Section-level (`book_slug`, `chapter`, `section`) |
| Settings sections visible | All 4 (account / tokens / annotations / data) |
| Settings actually wired | display_name, change_password, clear_progress, logout, cards-open-by-default |
| Settings visual-only | tokens section, change email, delete account, visible-categories filter |
| Post-login destination | `/library` |
| Admin migration | Old `ADMIN_PASSWORD_HASH` env var deprecated; admin becomes user_id=1 with `is_admin=true` |

## Architecture

Storage shifts from "JSON sidecars only" to **SQLite + JSON sidecars**:

- SQLite at `/var/www/belowiceberg-data/app.db` holds all per-user data.
- JSON sidecars at `/var/www/belowiceberg-data/notes/<slug>.json` continue to be the source of truth for **public, admin-authored** annotations. We do NOT migrate them.

This split keeps the public reading path simple (one fetch of static-ish JSON) and isolates user data behind auth.

### Tables (initial migration `001_users.sql`)

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  cards_open_default INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE user_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_slug TEXT NOT NULL,
  para_id TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('vocab','grammar','structure')),
  selected_text TEXT NOT NULL,
  response_markdown TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_user_notes_user ON user_notes(user_id);
CREATE INDEX idx_user_notes_user_book ON user_notes(user_id, book_slug);

CREATE TABLE reading_progress (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_slug TEXT NOT NULL,
  chapter INTEGER NOT NULL,
  section INTEGER NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, book_slug)
);
```

### Backend modules

```
server/app/
  db.py                      # SQLite connection + migration runner
  users.py                   # CRUD: create, verify, get, update, change_password, clear_progress
  user_notes.py              # CRUD: append, list for user (optionally per book)
  progress.py                # upsert; library aggregation query
  auth.py                    # extended: session cookie carries {user_id, exp}; require_user, require_admin
  routes/
    auth.py                  # /api/auth/{signup,login,logout}, /api/me, /api/me/change-password
    user_notes.py            # GET/POST /api/user-notes/<slug>
    progress.py              # POST /api/progress, GET /api/library
    notes.py                 # (existing) public sidecar — unchanged
    query.py                 # (existing) DeepSeek stream — gated changes to require_user
    admin.py                 # (existing) DEPRECATED — remove after migration
  cli/
    create_admin.py          # one-shot: insert user_id=1 as admin with chosen password
server/migrations/
  001_users.sql              # tables above
```

Each backend module owns one slice of state. Routes are thin — they validate input, call the module, return JSON. Tests target the modules directly + integration tests via FastAPI TestClient.

### Frontend modules

```
static/
  annotate-ui.js     # selection bar, popover, save dialog, hydration rendering
  annotate-data.js   # API calls (/api/notes, /api/user-notes, /api/query, /api/me, /api/progress)
  annotate.css       # (existing, extended)
login/
  index.html         # rewrite: replace OAuth-only mock with real email+password form
  styles.css         # keep
library/
  index.html         # NEW: copy design mock, wire to /api/library
  styles.css         # NEW: copy from design bundle
settings/
  index.html         # rewrite: keep all visual sections; wire scoped subset
  styles.css         # keep
```

`annotate.js` is split into `annotate-ui.js` (DOM, rendering) + `annotate-data.js` (API). The teaching-edition HTML loads both with `<script defer>`. This keeps each file under ~400 lines and lets us test the data layer in isolation.

## Auth model

Session cookie `belowiceberg_session`, HttpOnly, SameSite=Lax, 30-day expiry. Payload (signed by `itsdangerous`): `{"user_id": int, "v": 1}`. Validation also re-fetches the user from DB on every protected request (cheap; SQLite is local). If the user row is gone, treat as logged-out.

`require_user(session)` dependency returns the user dict or raises 401.
`require_admin(session)` returns the user only if `is_admin == 1`, else 403.

Password hashing: bcrypt, 12 rounds (matches existing usage).

Rate limiting on `/api/auth/login` and `/api/auth/signup`: 5 attempts/min/IP via an in-memory counter (acceptable for a single-server deploy).

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/signup` | none | `{email, password, display_name}` → 200 sets cookie, or 409 if email exists |
| POST | `/api/auth/login` | none | `{email, password}` → 200 sets cookie or 401 |
| POST | `/api/auth/logout` | session | clears cookie |
| GET  | `/api/me` | session | `{id, email, display_name, is_admin, cards_open_default}` |
| POST | `/api/me/change-password` | session | `{current, new}` → 200 or 401 |
| PATCH| `/api/me` | session | `{display_name?, cards_open_default?}` |
| POST | `/api/me/clear-progress` | session | deletes all `reading_progress` rows for this user |
| GET  | `/api/user-notes/<slug>` | session | array of this user's notes for this book |
| POST | `/api/user-notes/<slug>` | session | append a note |
| POST | `/api/progress` | session | `{book_slug, chapter, section}` upsert |
| GET  | `/api/library` | session | `{current: {slug, chapter, section, updated_at}, books_in_progress: [...], all_my_notes: [...], stats: {sessions, streak_days}}` |
| GET  | `/api/notes/<slug>` | none | (existing) public admin-authored notes |
| POST | `/api/notes/<slug>` | admin | (existing) appends to public sidecar — now gated on `is_admin` |
| POST | `/api/query` | session | (existing) streams DeepSeek — was admin, now any logged-in user |

`/admin/login`, `/admin/logout`, `/admin` (status) are removed after migration.

## Frontend flows

### `/login`

Email + password form (signup tab toggles to display_name field). On submit → POST, on success → `location.href = next_url || '/library'`. The existing visual design (Split Spread B) stays; the OAuth buttons become an inactive note: "Apple / Google 登录即将上线".

### `/gatsby` (and any book page)

On load: `annotate-data.js` fetches `/api/me`. If 200 → `state = {user, isAdmin}`. Else → anonymous.

Then in parallel:
- GET `/api/notes/<slug>` → render public notes (always, regardless of auth).
- If user → GET `/api/user-notes/<slug>` → render user's private notes (interleaved with public).

Selection bar only attaches if user. On save: `isAdmin && wantsPublic` → POST `/api/notes`; else → POST `/api/user-notes`. The popover footer shows the toggle "保存到个人 / 发布到所有读者" only when `isAdmin` (regular user only sees "保存"). Default for admin is "个人".

Progress: a single IntersectionObserver watches `.para-section` elements. When one crosses 50% visibility, a 1.5s debounce timer fires `POST /api/progress` with the para's chapter/section parsed from its id (e.g. `ch3s12` → ch:3, sec:12). Also fired on chapter-tab click.

### `/library`

Server-rendered HTML shell + a single JS file that fetches `/api/library` and populates. Sections:

- **Continue reading**: `current_book` block with cover, last position label ("第三章 · 第七节"), big "继续阅读" button linking to `/{slug}#ch{N}s{M}`.
- **All my notes**: paginated 20 per page (client-side slice since v1 won't have thousands), grouped by book then by chapter. Each item shows category color, selected text, response markdown.
- **Stats**: 累计阅读 (sum of reading-session-day counts derived from `updated_at`), 阅读次数 (count of distinct days with progress events), 连续阅读 (current consecutive-day streak).

Sample row count: a power user could have a few hundred notes — fits in one response easily.

### `/settings`

Server-rendered HTML (same visual sections as deployed mock). One JS file fetches `/api/me`, populates editable fields, wires:
- Display name field → PATCH `/api/me` on blur.
- Cards-open-by-default toggle → PATCH `/api/me` on change.
- 修改密码 button → opens inline form → POST `/api/me/change-password`.
- 清除阅读进度 → confirm dialog → POST `/api/me/clear-progress`.
- 退出登录 → POST `/api/auth/logout` → redirect to `/`.

Tokens section, change-email field, delete-account button, visible-categories chips: all present in markup but with `data-disabled="v1"` and a small "即将上线" hint on hover. No event handlers.

## Failure modes

- **Concurrent annotation save** by the same admin in two tabs: existing JSON-sidecar atomic write handles this; last write wins.
- **Stale session cookie** after user deletion / password change: validation re-fetches user; if row missing, treat as logged out and surface 401 → frontend redirects to `/login` on the next API call.
- **DB corruption**: backup recommendation — daily cron `sqlite3 app.db ".backup /backups/app-$(date +%F).db"` on the server (out of scope for code; mention in deploy docs).
- **DeepSeek error during user query**: same handling as today (popover shows error, nothing saved).
- **Reading-progress posts during fast scrolling**: debounced; only the last position per 1.5s window is sent.

## Migration plan

1. Deploy v1 code with both old admin routes AND new auth routes coexisting.
2. Run `python -m app.cli.create_admin` on the server, prompted for the admin email + new password. Creates user_id=1 with `is_admin=1`.
3. Test new login path. Admin can now sign in via `/login` like any user.
4. In a follow-up commit (after verification), remove `routes/admin.py` and the `ADMIN_PASSWORD_HASH` env var from `belowiceberg-api.service` and `/etc/belowiceberg/admin.env`.

Existing public annotation JSON sidecars on disk are untouched — they continue to load on `/gatsby` for all visitors.

## Open questions for the implementation plan

- Exact session cookie expiry behavior on password change (rotate sessions vs. let existing ones live)
- Whether the `/login` page should pre-populate `next=` from the referer when the redirect originated from a logged-in-gated action
- Whether the `cards_open_default` preference should apply to the `.card.open` initial state via inline CSS at SSR time, or via JS on hydration (JS is simpler; small flash)

---

Spec written. Please review and let me know if you want any changes before I have writing-plans turn this into a step-by-step implementation plan.
