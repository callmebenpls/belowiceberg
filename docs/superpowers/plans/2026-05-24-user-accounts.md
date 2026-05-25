# User Accounts & Logged-in Reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship email+password accounts, per-user AI annotations, per-user reading progress, a wired library page, and a partially-wired settings page — without breaking the existing public reading flow or the admin annotation publishing flow.

**Architecture:** Add SQLite at `/var/www/belowiceberg-data/app.db` for users/notes/progress; keep the existing JSON sidecars at `notes/<slug>.json` as the source of truth for public admin-authored annotations. Extend the existing FastAPI app with auth/user-notes/progress/library routes. Split `annotate.js` into `annotate-ui.js` + `annotate-data.js`. Migrate the single-admin password to user_id=1 with `is_admin=true`.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, sqlite3 (stdlib), bcrypt, itsdangerous, pytest, pytest-httpx, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-05-24-user-accounts-design.md`

---

## File Structure

```
server/
  app/
    db.py                    # NEW: sqlite3 connection + migration runner
    users.py                 # NEW: CRUD on users table
    user_notes.py            # NEW: CRUD on user_notes (per-user AI annotations)
    progress.py              # NEW: reading_progress upsert + library aggregation
    auth.py                  # MODIFY: session payload becomes {user_id, v}; add require_user
    config.py                # MODIFY: add ADMIN_PASSWORD_HASH deprecation note (don't break)
    main.py                  # MODIFY: include new routers; run migrations at startup
    notes.py                 # MODIFY: same; no logic change but tests now run alongside DB tests
    deepseek.py              # UNCHANGED
    routes/
      auth.py                # NEW: /api/auth/{signup,login,logout}, /api/me, /api/me/change-password, PATCH /api/me, /api/me/clear-progress
      user_notes.py          # NEW: /api/user-notes/<slug> GET+POST
      progress.py            # NEW: /api/progress POST, /api/library GET
      notes.py               # MODIFY: POST gated on is_admin (was admin-only login)
      query.py               # MODIFY: gated on require_user (was require_admin)
      admin.py               # KEEP for migration; remove after Task 19
  cli/
    __init__.py              # NEW (empty)
    create_admin.py          # NEW: one-shot interactive admin seeding
  migrations/
    001_users.sql            # NEW: tables for users, user_notes, reading_progress
  tests/
    conftest.py              # MODIFY: add `db` fixture using a tmp SQLite path
    test_db.py               # NEW
    test_users.py            # NEW
    test_user_notes.py       # NEW
    test_progress.py         # NEW
    test_auth.py             # MODIFY: new tests for require_user, session payload
    test_routes_auth.py      # NEW
    test_routes_user_notes.py# NEW
    test_routes_progress.py  # NEW
    test_routes.py           # MODIFY: update query test for new auth gate; rename old admin tests to "deprecated"
static/
  annotate-data.js           # NEW: API layer (fetch /api/me, hydrate, save, post progress)
  annotate-ui.js             # NEW: DOM (selection bar, popover) — split from existing annotate.js
  annotate.js                # MODIFY: thin boot that wires ui ↔ data; or delete and reference both new files
  annotate.css               # MODIFY: small additions for progress indicator (none for now)
login/
  index.html                 # REWRITE: replace OAuth-only mock with email+password form (keep Variation B visuals)
  styles.css                 # MODIFY: small additions for form fields, errors
library/
  index.html                 # NEW: copy from design bundle + wire to /api/library
  styles.css                 # NEW: copy from design bundle
settings/
  index.html                 # MODIFY: wire scoped subset
  styles.css                 # UNCHANGED
gatsby-teaching-edition.html # MODIFY: load both annotate-ui.js + annotate-data.js
belowiceberg-website-v2.html # MODIFY: same
```

**Boundaries:**
- `db.py` is the only module that talks to sqlite3 directly. Everything else takes a `conn` or uses module-level functions that call `get_conn()`.
- `users.py` / `user_notes.py` / `progress.py` know nothing about HTTP — pure data modules.
- `auth.py` produces/validates cookies; routes apply it as a `Depends()`.
- Frontend `annotate-data.js` is the only file that does `fetch()`; `annotate-ui.js` knows nothing about API shapes.

---

## Task 1: SQLite connection + migration runner

**Files:**
- Create: `server/app/db.py`
- Create: `server/migrations/001_users.sql`
- Create: `server/tests/test_db.py`
- Modify: `server/tests/conftest.py`

- [ ] **Step 1: Write migration SQL**

`server/migrations/001_users.sql`:
```sql
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  cards_open_default INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_slug TEXT NOT NULL,
  para_id TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('vocab','grammar','structure')),
  selected_text TEXT NOT NULL,
  response_markdown TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_user_notes_user ON user_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_user_notes_user_book ON user_notes(user_id, book_slug);

CREATE TABLE IF NOT EXISTS reading_progress (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_slug TEXT NOT NULL,
  chapter INTEGER NOT NULL,
  section INTEGER NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, book_slug)
);

INSERT OR IGNORE INTO schema_version (version) VALUES (1);
```

- [ ] **Step 2: Extend conftest with `db` fixture**

Append to `server/tests/conftest.py`:
```python
import pytest
from pathlib import Path

@pytest.fixture
def db(env, monkeypatch):
    """Fresh in-file SQLite per test, with migrations applied."""
    from app.db import migrate, get_conn, reset_conn
    reset_conn()  # clear any cached connection
    # `env` fixture already set BELOWICEBERG_DATA_DIR to tmp_path
    migrate()
    yield get_conn()
    reset_conn()
```

- [ ] **Step 3: Write failing tests**

`server/tests/test_db.py`:
```python
def test_migrate_creates_tables(db):
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    assert "users" in tables
    assert "user_notes" in tables
    assert "reading_progress" in tables
    assert "schema_version" in tables

def test_migrate_is_idempotent(db):
    from app.db import migrate
    migrate()  # second call should not error
    migrate()
    cur = db.execute("SELECT version FROM schema_version")
    assert cur.fetchone()[0] == 1

def test_get_conn_returns_same_connection_within_process(db):
    from app.db import get_conn
    assert get_conn() is get_conn()
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd /Users/ben/Downloads/belowiceberg/server && .venv/bin/pytest tests/test_db.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 5: Implement db.py**

`server/app/db.py`:
```python
import sqlite3
from pathlib import Path
from app.config import load_config

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

_conn: sqlite3.Connection | None = None

def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        cfg = load_config()
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        db_path = cfg.data_dir / "app.db"
        _conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.row_factory = sqlite3.Row
    return _conn

def reset_conn() -> None:
    """For tests: drop the cached connection so the next call reopens."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None

def _current_version(conn: sqlite3.Connection) -> int:
    try:
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0

def migrate() -> None:
    conn = get_conn()
    current = _current_version(conn)
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.name.split("_", 1)[0])
        if version <= current:
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_db.py -v
```
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add server/app/db.py server/migrations/ server/tests/test_db.py server/tests/conftest.py
git commit -m "feat(db): sqlite connection + idempotent migration runner"
```

---

## Task 2: Users module (CRUD)

**Files:**
- Create: `server/app/users.py`
- Create: `server/tests/test_users.py`

- [ ] **Step 1: Write failing tests**

`server/tests/test_users.py`:
```python
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
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_users.py -v
```
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement users.py**

`server/app/users.py`:
```python
import bcrypt
from typing import Optional
from app.db import get_conn

class UserExistsError(ValueError): pass
class UserNotFoundError(LookupError): pass
class WrongPasswordError(ValueError): pass

def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()

def _check(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False

def create_user(email: str, password: str, display_name: str, is_admin: bool = False) -> int:
    email = email.strip().lower()
    if not email or not password or not display_name:
        raise ValueError("email, password, display_name required")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users(email, password_hash, display_name, is_admin) VALUES (?,?,?,?)",
            (email, _hash(password), display_name, 1 if is_admin else 0),
        )
        return cur.lastrowid
    except Exception as e:
        if "UNIQUE" in str(e):
            raise UserExistsError(f"email already registered: {email}")
        raise

def get_by_id(user_id: int) -> dict:
    row = get_conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise UserNotFoundError(f"no user {user_id}")
    return dict(row)

def get_by_email(email: str) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    return dict(row) if row else None

def verify_credentials(email: str, password: str) -> Optional[int]:
    u = get_by_email(email)
    if not u:
        return None
    if not _check(password, u["password_hash"]):
        return None
    return u["id"]

def update_display_name(user_id: int, name: str) -> None:
    get_conn().execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))

def update_cards_open_default(user_id: int, value: bool) -> None:
    get_conn().execute("UPDATE users SET cards_open_default = ? WHERE id = ?",
                       (1 if value else 0, user_id))

def change_password(user_id: int, current: str, new: str) -> None:
    if len(new) < 8:
        raise ValueError("new password must be at least 8 characters")
    u = get_by_id(user_id)
    if not _check(current, u["password_hash"]):
        raise WrongPasswordError("current password is wrong")
    get_conn().execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (_hash(new), user_id))

def clear_progress(user_id: int) -> None:
    get_conn().execute("DELETE FROM reading_progress WHERE user_id = ?", (user_id,))

def delete_user(user_id: int) -> None:
    get_conn().execute("DELETE FROM users WHERE id = ?", (user_id,))
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/pytest tests/test_users.py -v
```
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add server/app/users.py server/tests/test_users.py
git commit -m "feat(users): CRUD with bcrypt hashing and cascading deletes"
```

---

## Task 3: Extend auth.py for user sessions

**Files:**
- Modify: `server/app/auth.py`
- Modify: `server/tests/test_auth.py`

- [ ] **Step 1: Append new failing tests**

Append to `server/tests/test_auth.py`:
```python
from app.auth import issue_user_session, validate_user_session

def test_user_session_roundtrip(env):
    token = issue_user_session(user_id=42)
    assert validate_user_session(token) == 42

def test_user_session_rejects_tampered(env):
    token = issue_user_session(user_id=42)
    bad = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert validate_user_session(bad) is None

def test_user_session_rejects_empty(env):
    assert validate_user_session("") is None
    assert validate_user_session(None) is None
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_auth.py -v
```
Expected: 3 new tests FAIL (ImportError on `issue_user_session`).

- [ ] **Step 3: Modify auth.py — add user session helpers**

Read `server/app/auth.py`. Append (do NOT delete the existing `verify_password`, `issue_session`, `validate_session`, `require_admin` — they stay for now, removed later in Task 19):

```python
# ─── User sessions (new) ────────────────────────────────────────────
from fastapi import Depends

def issue_user_session(user_id: int) -> str:
    return _serializer().dumps({"user_id": int(user_id), "v": 1})

def validate_user_session(token: str | None) -> int | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
        if data.get("v") != 1:
            return None
        return int(data["user_id"])
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None

def require_user(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    """FastAPI dependency. Returns the user row dict; raises 401 if no/invalid session."""
    from app.users import get_by_id, UserNotFoundError
    uid = validate_user_session(session)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    try:
        return get_by_id(uid)
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")

def require_admin_user(user: dict = Depends(require_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin only")
    return user
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/pytest tests/test_auth.py -v
```
Expected: all pass (old 5 + new 3 = 8).

- [ ] **Step 5: Commit**

```bash
git add server/app/auth.py server/tests/test_auth.py
git commit -m "feat(auth): add user-session helpers and require_user/require_admin_user dependencies"
```

---

## Task 4: Auth routes — signup + login + logout + me

**Files:**
- Create: `server/app/routes/auth.py`
- Modify: `server/app/main.py` (register router)
- Create: `server/tests/test_routes_auth.py`

- [ ] **Step 1: Write failing tests**

`server/tests/test_routes_auth.py`:
```python
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth import SESSION_COOKIE

@pytest.fixture
def client(env, db):
    return TestClient(create_app())

def test_signup_creates_user_and_sets_cookie(client):
    r = client.post("/api/auth/signup", json={
        "email": "a@b.com", "password": "secret123", "display_name": "Ann"
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert SESSION_COOKIE in r.cookies

def test_signup_duplicate_email_409(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "B"})
    assert r.status_code == 409

def test_signup_rejects_short_password(client):
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "abc", "display_name": "A"})
    assert r.status_code == 400

def test_login_ok_sets_cookie(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/auth/login", json={"email": "a@b.com", "password": "secret123"})
    assert r.status_code == 200
    assert SESSION_COOKIE in r.cookies

def test_login_wrong_password_401(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong"})
    assert r.status_code == 401

def test_me_requires_session(client):
    assert client.get("/api/me").status_code == 401

def test_me_returns_profile(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "Ann"})
    r = client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "a@b.com"
    assert body["display_name"] == "Ann"
    assert body["is_admin"] is False
    assert body["cards_open_default"] is True

def test_logout_clears_cookie(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    assert client.get("/api/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401

def test_change_password_ok(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/me/change-password", json={"current": "secret123", "new": "newpw456"})
    assert r.status_code == 200
    # log out, log in with new
    client.post("/api/auth/logout")
    r2 = client.post("/api/auth/login", json={"email": "a@b.com", "password": "newpw456"})
    assert r2.status_code == 200

def test_change_password_wrong_current(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.post("/api/me/change-password", json={"current": "WRONG", "new": "newpw456"})
    assert r.status_code == 401

def test_patch_me_updates_display_name(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "Old"})
    r = client.patch("/api/me", json={"display_name": "New"})
    assert r.status_code == 200
    assert client.get("/api/me").json()["display_name"] == "New"

def test_patch_me_updates_cards_open_default(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    r = client.patch("/api/me", json={"cards_open_default": False})
    assert r.status_code == 200
    assert client.get("/api/me").json()["cards_open_default"] is False

def test_clear_progress_endpoint(client, db):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})
    me = client.get("/api/me").json()
    db.execute("INSERT INTO reading_progress(user_id, book_slug, chapter, section) VALUES (?,?,?,?)",
               (me["id"], "gatsby", 1, 1))
    r = client.post("/api/me/clear-progress")
    assert r.status_code == 200
    rows = db.execute("SELECT 1 FROM reading_progress WHERE user_id = ?", (me["id"],)).fetchone()
    assert rows is None
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_routes_auth.py -v
```
Expected: FAIL with 404s (router not registered).

- [ ] **Step 3: Implement routes/auth.py**

`server/app/routes/auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status
from pydantic import BaseModel, EmailStr, Field
from app.auth import (
    SESSION_COOKIE, SESSION_MAX_AGE,
    issue_user_session, require_user,
)
from app import users as users_mod

router = APIRouter()

class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=64)

class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

class ChangePasswordBody(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    new: str = Field(min_length=8, max_length=200)

class PatchMeBody(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    cards_open_default: bool | None = None

def _set_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE, value=issue_user_session(user_id),
        max_age=SESSION_MAX_AGE, httponly=True,
        samesite="lax", secure=False, path="/",
    )

def _user_to_json(u: dict) -> dict:
    return {
        "id": u["id"], "email": u["email"], "display_name": u["display_name"],
        "is_admin": bool(u["is_admin"]),
        "cards_open_default": bool(u["cards_open_default"]),
    }

@router.post("/api/auth/signup")
def signup(body: SignupBody, response: Response):
    try:
        uid = users_mod.create_user(body.email, body.password, body.display_name)
    except users_mod.UserExistsError:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="email already registered")
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    _set_cookie(response, uid)
    return {"ok": True}

@router.post("/api/auth/login")
def login(body: LoginBody, response: Response):
    uid = users_mod.verify_credentials(body.email, body.password)
    if uid is None:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="bad credentials")
    _set_cookie(response, uid)
    return {"ok": True}

@router.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}

@router.get("/api/me")
def me(user: dict = Depends(require_user)):
    return _user_to_json(user)

@router.patch("/api/me")
def patch_me(body: PatchMeBody, user: dict = Depends(require_user)):
    if body.display_name is not None:
        users_mod.update_display_name(user["id"], body.display_name)
    if body.cards_open_default is not None:
        users_mod.update_cards_open_default(user["id"], body.cards_open_default)
    return {"ok": True}

@router.post("/api/me/change-password")
def change_password_route(body: ChangePasswordBody, user: dict = Depends(require_user)):
    try:
        users_mod.change_password(user["id"], body.current, body.new)
    except users_mod.WrongPasswordError:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="wrong current password")
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True}

@router.post("/api/me/clear-progress")
def clear_progress_route(user: dict = Depends(require_user)):
    users_mod.clear_progress(user["id"])
    return {"ok": True}
```

- [ ] **Step 4: Modify main.py — run migrations + register router**

Read `server/app/main.py`. Replace the function body with:
```python
from fastapi import FastAPI
from app.db import migrate
from app.routes import admin, notes, query
from app.routes import auth as auth_routes

def create_app() -> FastAPI:
    migrate()
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)        # legacy, removed in Task 19
    app.include_router(notes.router)
    app.include_router(query.router)
    app.include_router(auth_routes.router)
    return app

app = create_app()
```

- [ ] **Step 5: Install email-validator (dependency of pydantic EmailStr)**

```bash
cd /Users/ben/Downloads/belowiceberg/server
.venv/bin/pip install "email-validator>=2.0"
```

Then add to `server/pyproject.toml` `dependencies` list:
```toml
  "email-validator>=2.0",
```

- [ ] **Step 6: Run to verify pass**

```bash
.venv/bin/pytest tests/test_routes_auth.py -v
```
Expected: 13 passed.

- [ ] **Step 7: Commit**

```bash
git add server/app/routes/auth.py server/app/main.py server/pyproject.toml server/tests/test_routes_auth.py
git commit -m "feat(api): signup/login/logout/me/change-password/clear-progress endpoints"
```

---

## Task 5: User notes module

**Files:**
- Create: `server/app/user_notes.py`
- Create: `server/tests/test_user_notes.py`

- [ ] **Step 1: Write failing tests**

`server/tests/test_user_notes.py`:
```python
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
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_user_notes.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement user_notes.py**

`server/app/user_notes.py`:
```python
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
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/pytest tests/test_user_notes.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add server/app/user_notes.py server/tests/test_user_notes.py
git commit -m "feat(user_notes): per-user annotation CRUD with slug/category validation"
```

---

## Task 6: User notes routes

**Files:**
- Create: `server/app/routes/user_notes.py`
- Modify: `server/app/main.py`
- Create: `server/tests/test_routes_user_notes.py`

- [ ] **Step 1: Write failing tests**

`server/tests/test_routes_user_notes.py`:
```python
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(env, db):
    return TestClient(create_app())

def _login(client, email="a@b.com"):
    client.post("/api/auth/signup", json={"email": email, "password": "secret123", "display_name": "A"})

def test_user_notes_requires_login(client):
    assert client.get("/api/user-notes/gatsby").status_code == 401
    assert client.post("/api/user-notes/gatsby", json={}).status_code == 401

def test_post_then_get_returns_only_my_notes(client):
    _login(client, "a@b.com")
    note = {"paraId": "p1", "category": "vocab",
            "selectedText": "x", "responseMarkdown": "y"}
    r = client.post("/api/user-notes/gatsby", json=note)
    assert r.status_code == 201
    r2 = client.get("/api/user-notes/gatsby")
    assert r2.status_code == 200
    body = r2.json()
    assert len(body) == 1
    assert body[0]["selectedText"] == "x"
    assert "createdAt" in body[0]

def test_other_user_does_not_see_my_notes(client):
    _login(client, "a@b.com")
    client.post("/api/user-notes/gatsby", json={"paraId": "p","category":"vocab","selectedText":"x","responseMarkdown":"y"})
    client.post("/api/auth/logout")
    _login(client, "b@b.com")
    assert client.get("/api/user-notes/gatsby").json() == []

def test_post_bad_category(client):
    _login(client)
    r = client.post("/api/user-notes/gatsby",
                    json={"paraId":"p","category":"bogus","selectedText":"x","responseMarkdown":"y"})
    assert r.status_code == 422  # pydantic Literal rejection

def test_post_bad_slug(client):
    _login(client)
    r = client.post("/api/user-notes/..etc",
                    json={"paraId":"p","category":"vocab","selectedText":"x","responseMarkdown":"y"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_routes_user_notes.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement routes/user_notes.py**

`server/app/routes/user_notes.py`:
```python
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field
from app.auth import require_user
from app import user_notes as un

router = APIRouter()

class NoteIn(BaseModel):
    paraId: str = Field(min_length=1, max_length=64)
    category: Literal["vocab", "grammar", "structure"]
    selectedText: str = Field(min_length=1, max_length=2000)
    responseMarkdown: str = Field(min_length=1, max_length=8000)

def _row_to_json(r: dict) -> dict:
    return {
        "id": r["id"], "book_slug": r["book_slug"],
        "paraId": r["para_id"], "category": r["category"],
        "selectedText": r["selected_text"],
        "responseMarkdown": r["response_markdown"],
        "createdAt": r["created_at"],
    }

@router.get("/api/user-notes/{slug}")
def get_user_notes(slug: str, user: dict = Depends(require_user)):
    try:
        return [_row_to_json(r) for r in un.list_for_user_book(user["id"], slug)]
    except un.UserNoteError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/api/user-notes/{slug}", status_code=http_status.HTTP_201_CREATED)
def post_user_note(slug: str, body: NoteIn, user: dict = Depends(require_user)):
    try:
        nid = un.append_note(user["id"], slug, body.paraId, body.category,
                             body.selectedText, body.responseMarkdown)
    except un.UserNoteError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True, "id": nid}
```

- [ ] **Step 4: Register in main.py**

Replace `server/app/main.py`:
```python
from fastapi import FastAPI
from app.db import migrate
from app.routes import admin, notes, query
from app.routes import auth as auth_routes
from app.routes import user_notes as user_notes_routes

def create_app() -> FastAPI:
    migrate()
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    app.include_router(query.router)
    app.include_router(auth_routes.router)
    app.include_router(user_notes_routes.router)
    return app

app = create_app()
```

- [ ] **Step 5: Run to verify pass**

```bash
.venv/bin/pytest tests/test_routes_user_notes.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/user_notes.py server/app/main.py server/tests/test_routes_user_notes.py
git commit -m "feat(api): per-user notes endpoints (GET/POST /api/user-notes/<slug>)"
```

---

## Task 7: Progress module + library aggregation

**Files:**
- Create: `server/app/progress.py`
- Create: `server/tests/test_progress.py`

- [ ] **Step 1: Write failing tests**

`server/tests/test_progress.py`:
```python
import pytest
from app.progress import upsert_progress, get_library_for, ProgressError

def _mk_user(db, email="a@b.com"):
    from app.users import create_user
    return create_user(email, "secret123", "A")

def test_upsert_creates_then_updates(db):
    uid = _mk_user(db)
    upsert_progress(uid, "gatsby", 1, 5)
    upsert_progress(uid, "gatsby", 2, 1)
    rows = db.execute("SELECT chapter, section FROM reading_progress WHERE user_id = ?", (uid,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["chapter"] == 2
    assert rows[0]["section"] == 1

def test_upsert_different_books_separate_rows(db):
    uid = _mk_user(db)
    upsert_progress(uid, "gatsby", 1, 5)
    upsert_progress(uid, "henry",  2, 3)
    rows = db.execute("SELECT book_slug FROM reading_progress WHERE user_id = ?", (uid,)).fetchall()
    assert {r["book_slug"] for r in rows} == {"gatsby", "henry"}

def test_get_library_for_empty(db):
    uid = _mk_user(db)
    lib = get_library_for(uid)
    assert lib["current"] is None
    assert lib["books_in_progress"] == []
    assert lib["all_my_notes"] == []
    assert lib["stats"]["sessions"] == 0
    assert lib["stats"]["streak_days"] == 0

def test_get_library_picks_most_recent_as_current(db):
    uid = _mk_user(db)
    upsert_progress(uid, "gatsby", 1, 1)
    import time; time.sleep(1.1)
    upsert_progress(uid, "henry", 2, 2)
    lib = get_library_for(uid)
    assert lib["current"]["book_slug"] == "henry"
    assert {b["book_slug"] for b in lib["books_in_progress"]} == {"gatsby", "henry"}

def test_get_library_includes_notes(db):
    from app.user_notes import append_note
    uid = _mk_user(db)
    append_note(uid, "gatsby", "p1", "vocab", "x", "y")
    lib = get_library_for(uid)
    assert len(lib["all_my_notes"]) == 1

def test_upsert_rejects_bad_slug(db):
    uid = _mk_user(db)
    with pytest.raises(ProgressError):
        upsert_progress(uid, "../etc", 1, 1)

def test_upsert_rejects_bad_numbers(db):
    uid = _mk_user(db)
    with pytest.raises(ProgressError):
        upsert_progress(uid, "gatsby", 0, 1)
    with pytest.raises(ProgressError):
        upsert_progress(uid, "gatsby", 1, 0)
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_progress.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement progress.py**

`server/app/progress.py`:
```python
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
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/pytest tests/test_progress.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add server/app/progress.py server/tests/test_progress.py
git commit -m "feat(progress): reading-progress upsert + library aggregation with sessions/streak"
```

---

## Task 8: Progress + library routes

**Files:**
- Create: `server/app/routes/progress.py`
- Modify: `server/app/main.py`
- Create: `server/tests/test_routes_progress.py`

- [ ] **Step 1: Write failing tests**

`server/tests/test_routes_progress.py`:
```python
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(env, db):
    return TestClient(create_app())

def _login(client):
    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "secret123", "display_name": "A"})

def test_progress_requires_login(client):
    assert client.post("/api/progress", json={"book_slug": "gatsby", "chapter": 1, "section": 1}).status_code == 401
    assert client.get("/api/library").status_code == 401

def test_post_progress_then_library(client):
    _login(client)
    r = client.post("/api/progress", json={"book_slug": "gatsby", "chapter": 3, "section": 7})
    assert r.status_code == 200
    lib = client.get("/api/library").json()
    assert lib["current"]["book_slug"] == "gatsby"
    assert lib["current"]["chapter"] == 3
    assert lib["current"]["section"] == 7

def test_library_includes_notes(client):
    _login(client)
    client.post("/api/user-notes/gatsby", json={"paraId":"p","category":"vocab","selectedText":"x","responseMarkdown":"y"})
    lib = client.get("/api/library").json()
    assert len(lib["all_my_notes"]) == 1

def test_post_progress_bad_input(client):
    _login(client)
    r = client.post("/api/progress", json={"book_slug": "../etc", "chapter": 1, "section": 1})
    assert r.status_code == 400
    r2 = client.post("/api/progress", json={"book_slug": "gatsby", "chapter": 0, "section": 1})
    assert r2.status_code == 400
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_routes_progress.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement routes/progress.py**

`server/app/routes/progress.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field
from app.auth import require_user
from app import progress as prog

router = APIRouter()

class ProgressBody(BaseModel):
    book_slug: str = Field(min_length=1, max_length=64)
    chapter: int = Field(ge=1, le=99)
    section: int = Field(ge=1, le=999)

@router.post("/api/progress")
def post_progress(body: ProgressBody, user: dict = Depends(require_user)):
    try:
        prog.upsert_progress(user["id"], body.book_slug, body.chapter, body.section)
    except prog.ProgressError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True}

@router.get("/api/library")
def get_library(user: dict = Depends(require_user)):
    return prog.get_library_for(user["id"])
```

- [ ] **Step 4: Register in main.py**

Replace `server/app/main.py`:
```python
from fastapi import FastAPI
from app.db import migrate
from app.routes import admin, notes, query
from app.routes import auth as auth_routes
from app.routes import user_notes as user_notes_routes
from app.routes import progress as progress_routes

def create_app() -> FastAPI:
    migrate()
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    app.include_router(query.router)
    app.include_router(auth_routes.router)
    app.include_router(user_notes_routes.router)
    app.include_router(progress_routes.router)
    return app

app = create_app()
```

- [ ] **Step 5: Run to verify pass**

```bash
.venv/bin/pytest tests/test_routes_progress.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/progress.py server/app/main.py server/tests/test_routes_progress.py
git commit -m "feat(api): /api/progress upsert and /api/library aggregate"
```

---

## Task 9: Re-gate existing query + public-notes routes

The `/api/query` endpoint was admin-only (Old `require_admin`). It now must be open to any logged-in user. The `POST /api/notes/<slug>` (public sidecar) was admin-only via old admin auth; now it must check `is_admin` on the *new* user table.

**Files:**
- Modify: `server/app/routes/query.py`
- Modify: `server/app/routes/notes.py`
- Modify: `server/tests/test_routes.py`

- [ ] **Step 1: Update test_routes.py to use new auth**

Edit `server/tests/test_routes.py`. Replace the `_login(client)` helper and adjust the existing admin/query tests:

```python
# at top of file, after existing imports
def _signup(client, email="admin@b.com", admin_via_db=False):
    """Sign up via the new auth route. If admin_via_db, flip is_admin in DB."""
    client.post("/api/auth/signup", json={"email": email, "password": "secret123", "display_name": "T"})
    if admin_via_db:
        from app.db import get_conn
        get_conn().execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))

# Replace the old `_login(client)` helper with this version (keep name for diff minimal)
def _login(client):
    _signup(client, admin_via_db=True)  # legacy tests assume the cookie holder is admin
```

Add the `db` fixture to existing tests that use `_login`:
```python
@pytest.fixture
def client(env, db):  # was: client(env)
    return TestClient(create_app())
```

- [ ] **Step 2: Run existing tests to verify they fail (or pass already)**

```bash
.venv/bin/pytest tests/test_routes.py -v
```
Expected: some tests now FAIL because the old `/admin/login` route still expects the old session shape but tests use new signup. That's the point of this task — to migrate.

- [ ] **Step 3: Modify query.py to use require_user**

Read `server/app/routes/query.py`. Replace the dependency:
```python
# was: from app.auth import require_admin
from app.auth import require_user
# ...
@router.post("/api/query")
async def query(body: QueryBody, _: dict = Depends(require_user)):
    return StreamingResponse(_sse(body), media_type="text/event-stream")
```

- [ ] **Step 4: Modify notes.py POST to use require_admin_user**

Read `server/app/routes/notes.py`. Replace:
```python
from app.auth import require_admin_user
# ...
@router.post("/api/notes/{slug}", status_code=status.HTTP_201_CREATED)
def post_note(slug: str, body: NoteIn, _: dict = Depends(require_admin_user)):
    # body unchanged
```

(`GET /api/notes/<slug>` stays public — no Depends.)

- [ ] **Step 5: Delete the legacy admin-route tests in test_routes.py**

In `server/tests/test_routes.py`, delete (or rename to `xtest_…`) these specific tests that exercised the old admin login flow:
- `test_login_wrong_password`
- `test_login_correct_sets_cookie`
- `test_admin_status_requires_session`
- `test_admin_status_with_session`
- `test_logout_clears_cookie`

The admin login flow is now covered by `tests/test_routes_auth.py`.

- [ ] **Step 6: Run all tests to verify pass**

```bash
.venv/bin/pytest -v
```
Expected: all tests across all files pass.

- [ ] **Step 7: Commit**

```bash
git add server/app/routes/query.py server/app/routes/notes.py server/tests/test_routes.py
git commit -m "refactor(auth): gate /api/query on require_user, POST /api/notes on require_admin_user; drop legacy admin login tests"
```

---

## Task 10: create_admin CLI

One-shot interactive script to seed the first admin user during migration.

**Files:**
- Create: `server/app/cli/__init__.py` (empty)
- Create: `server/app/cli/create_admin.py`

- [ ] **Step 1: Write empty package init**

```bash
touch /Users/ben/Downloads/belowiceberg/server/app/cli/__init__.py
```

- [ ] **Step 2: Write create_admin.py**

`server/app/cli/create_admin.py`:
```python
"""Seed an admin user. Run on the server:

  cd /opt/belowiceberg/server && .venv/bin/python -m app.cli.create_admin
"""
import getpass
import sys
from app.db import migrate
from app import users as users_mod

def main():
    migrate()
    email = input("Admin email: ").strip()
    name  = input("Display name: ").strip()
    pw1 = getpass.getpass("Password (8+ chars): ")
    pw2 = getpass.getpass("Confirm: ")
    if pw1 != pw2:
        sys.exit("password mismatch")
    if len(pw1) < 8:
        sys.exit("password too short")
    existing = users_mod.get_by_email(email)
    if existing:
        confirm = input(f"User {email} exists. Reset password and promote to admin? [y/N] ").strip().lower()
        if confirm != "y":
            sys.exit("aborted")
        from app.db import get_conn
        from app.users import _hash
        get_conn().execute(
            "UPDATE users SET password_hash = ?, is_admin = 1, display_name = ? WHERE id = ?",
            (_hash(pw1), name, existing["id"]),
        )
        print(f"Updated user {existing['id']} ({email}) as admin.")
    else:
        uid = users_mod.create_user(email, pw1, name, is_admin=True)
        print(f"Created user {uid} ({email}) as admin.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke-run locally (will refuse without env)**

```bash
cd /Users/ben/Downloads/belowiceberg/server
.venv/bin/python -c "from app.cli import create_admin; print('imports OK')"
```
Expected: prints `imports OK`.

- [ ] **Step 4: Commit**

```bash
git add server/app/cli/
git commit -m "feat(cli): interactive create_admin for seeding the first admin user"
```

---

## Task 11: Split annotate.js into ui + data

Today `static/annotate.js` is one big file. Splitting it lets us add user-aware behavior without bloating one file beyond comprehension.

**Files:**
- Create: `static/annotate-data.js`
- Create: `static/annotate-ui.js`
- Modify: `static/annotate.js` (becomes a thin shim that wires the two together, or is deleted in favor of two `<script>` tags)
- Modify: `gatsby-teaching-edition.html` + `belowiceberg-website-v2.html` (load both new files)

- [ ] **Step 1: Create annotate-data.js (API layer)**

`static/annotate-data.js`:
```javascript
// API + state layer. Exposes window.BIData with all fetch logic.
(() => {
  const BOOK_SLUG = (location.pathname.replace(/^\/+|\/+$/g, '').split('/')[0] || 'index')
                      .replace(/\.html$/, '');

  let _me = null;  // {id, display_name, is_admin, ...} or null

  async function fetchMe() {
    try {
      const r = await fetch('/api/me', { credentials: 'same-origin' });
      _me = r.ok ? await r.json() : null;
    } catch (_) { _me = null; }
    return _me;
  }

  async function fetchPublicNotes() {
    try {
      const r = await fetch(`/api/notes/${BOOK_SLUG}`);
      return r.ok ? await r.json() : [];
    } catch (_) { return []; }
  }

  async function fetchUserNotes() {
    if (!_me) return [];
    try {
      const r = await fetch(`/api/user-notes/${BOOK_SLUG}`, { credentials: 'same-origin' });
      return r.ok ? await r.json() : [];
    } catch (_) { return []; }
  }

  async function savePublicNote(note) {
    const r = await fetch(`/api/notes/${BOOK_SLUG}`, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(note),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  }

  async function saveUserNote(note) {
    const r = await fetch(`/api/user-notes/${BOOK_SLUG}`, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(note),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  }

  async function postProgress(chapter, section) {
    if (!_me) return;
    try {
      await fetch('/api/progress', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({book_slug: BOOK_SLUG, chapter, section}),
      });
    } catch (_) { /* silent */ }
  }

  async function streamQuery(category, selectedText, paraContext, onToken, onDone, onError) {
    try {
      const r = await fetch('/api/query', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ category, selectedText, paraContext }),
      });
      if (!r.ok) { onError(`HTTP ${r.status}`); return; }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split('\n\n');
        buf = events.pop();
        for (const ev of events) {
          for (const line of ev.split('\n')) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') { onDone(); return; }
              onToken(data.replace(/\\n/g, '\n'));
            }
          }
        }
      }
      onDone();
    } catch (e) { onError(e.message); }
  }

  window.BIData = {
    BOOK_SLUG,
    get me() { return _me; },
    fetchMe, fetchPublicNotes, fetchUserNotes,
    savePublicNote, saveUserNote, postProgress, streamQuery,
  };
})();
```

- [ ] **Step 2: Create annotate-ui.js (DOM layer)**

`static/annotate-ui.js`:
```javascript
// DOM layer. Selection bar, popover, hydration rendering, structure-card repair,
// progress observer. Depends on window.BIData being loaded first.
(() => {
  const D = window.BIData;
  const CATEGORIES = [
    { key: 'vocab',     label: '词汇',       dot: 'v', color: '#3a7bb5' },
    { key: 'grammar',   label: '语法',       dot: 'g', color: '#b8924a' },
    { key: 'structure', label: '句子结构',   dot: 's', color: '#7a8a4e' },
  ];
  const KIND_CLASS = { vocab: 'vocab', grammar: 'gram', structure: 'structure' };
  const KIND_LABEL = { vocab: '词汇', grammar: '语法', structure: '句子结构' };

  function mdToHtml(md) {
    let s = escapeHtml(md);
    s = s.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^\*])\*([^\*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    const paras = s.split(/\n{2,}/).map(p => `<p class="ann-line">${p.replace(/\n/g,'<br>')}</p>`);
    return paras.join('');
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function repairStructureCards() {
    document.querySelectorAll('.card-hdr.structure').forEach(hdr => {
      const card = hdr.closest('.card');
      if (!card) return;
      if (card.querySelector(':scope > .card-body')) return;
      const body = document.createElement('div');
      body.className = 'card-body';
      let n = hdr.nextSibling;
      while (n) { const next = n.nextSibling; body.appendChild(n); n = next; }
      card.appendChild(body);
    });
  }

  function renderSavedNote(note) {
    const para = document.getElementById(note.paraId);
    if (!para) return;
    const kindCls = KIND_CLASS[note.category] || note.category;
    const label = KIND_LABEL[note.category] || note.category;
    const card = document.createElement('div');
    card.className = 'card open bi-ai-card';
    card.innerHTML = `
      <div class="card-hdr ${kindCls}" onclick="(function(h){h.closest('.card').classList.toggle('open')})(this)">
        <span class="cat-badge">${label}</span>
        <span class="card-term">${escapeHtml(note.selectedText)}</span>
        <span class="card-toggle">▼</span>
      </div>
      <div class="card-body">${mdToHtml(note.responseMarkdown)}</div>
    `;
    para.appendChild(card);
  }

  // ─── Selection bar + popover ─────────────────────────────────────
  let currentBar = null, currentPop = null;
  function teardown() {
    if (currentBar) { currentBar.remove(); currentBar = null; }
    if (currentPop) { currentPop.remove(); currentPop = null; }
  }

  document.addEventListener('mouseup', (e) => {
    if (!D.me) return;
    if (currentPop && currentPop.contains(e.target)) return;
    if (currentBar && currentBar.contains(e.target)) return;
    setTimeout(() => handleSelection(e), 0);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') teardown(); });
  document.addEventListener('mousedown', (e) => {
    if (currentPop && currentPop.contains(e.target)) return;
    if (currentBar && currentBar.contains(e.target)) return;
    teardown();
  });

  function handleSelection(e) {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    const text = sel.toString().trim();
    if (!text) return;
    const range = sel.getRangeAt(0);
    const para = findParaSection(range.startContainer);
    if (!para) return;
    if (findParaSection(range.endContainer) !== para) return;
    teardown();
    showBar(range.getBoundingClientRect(), para, text);
  }

  function findParaSection(node) {
    while (node && node.nodeType !== 1) node = node.parentNode;
    return node ? node.closest('.para-section') : null;
  }

  function showBar(rect, para, text) {
    const bar = document.createElement('div');
    bar.className = 'bi-sel-bar';
    bar.style.top  = (window.scrollY + rect.top - 42) + 'px';
    bar.style.left = (window.scrollX + rect.left) + 'px';
    CATEGORIES.forEach(c => {
      const btn = document.createElement('button');
      btn.innerHTML = `<span class="dot ${c.dot}"></span>${c.label}`;
      btn.onclick = (ev) => { ev.stopPropagation(); bar.remove(); currentBar = null; openPopover(rect, para, text, c); };
      bar.appendChild(btn);
    });
    document.body.appendChild(bar);
    currentBar = bar;
  }

  function openPopover(rect, para, text, cat) {
    const isAdmin = !!(D.me && D.me.is_admin);
    const pop = document.createElement('div');
    pop.className = 'bi-pop';
    pop.style.top  = (window.scrollY + rect.bottom + 8) + 'px';
    pop.style.left = (window.scrollX + rect.left) + 'px';
    const scopeRow = isAdmin
      ? `<div class="bi-pop-scope">
           <label><input type="radio" name="bi-scope" value="private" checked> 保存到个人</label>
           <label><input type="radio" name="bi-scope" value="public"> 发布到所有读者</label>
         </div>`
      : '';
    pop.innerHTML = `
      <div class="bi-pop-hdr">
        <span><span class="cat" style="color:${cat.color}">${cat.label}</span> · DeepSeek</span>
        <span>${para.id}</span>
      </div>
      <div class="bi-pop-sel">"${escapeHtml(text)}"</div>
      <div class="bi-pop-body"></div>
      ${scopeRow}
      <div class="bi-pop-foot">
        <button class="bi-close">关闭</button>
        <button class="bi-save primary" disabled>保存</button>
      </div>
    `;
    document.body.appendChild(pop);
    currentPop = pop;
    const bodyEl  = pop.querySelector('.bi-pop-body');
    const saveBtn = pop.querySelector('.bi-save');
    const closeBtn = pop.querySelector('.bi-close');

    bodyEl.innerHTML = '<div class="bi-stream"></div><span class="bi-cursor"></span>';
    const streamEl = bodyEl.querySelector('.bi-stream');
    const cursorEl = bodyEl.querySelector('.bi-cursor');
    let raw = '';
    const paraText = (para.querySelector('.original') || para).innerText.trim();

    D.streamQuery(cat.key, text, paraText,
      (tok) => { raw += tok; streamEl.innerHTML = mdToHtml(raw); },
      () => { cursorEl.remove(); saveBtn.disabled = false; saveBtn.dataset.raw = raw; },
      (err) => { bodyEl.innerHTML = `<div class="bi-pop-err">出错：${escapeHtml(err)}</div>`; }
    );

    closeBtn.onclick = teardown;
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      const note = {
        paraId: para.id, category: cat.key,
        selectedText: text, responseMarkdown: saveBtn.dataset.raw || streamEl.innerText,
      };
      try {
        const scope = isAdmin
          ? (pop.querySelector('input[name="bi-scope"]:checked')?.value || 'private')
          : 'private';
        if (scope === 'public') await D.savePublicNote(note);
        else await D.saveUserNote(note);
        renderSavedNote(note);
        teardown();
      } catch (e) {
        alert('保存失败: ' + e.message);
        saveBtn.disabled = false;
      }
    };
  }

  // ─── Reading-progress observer ───────────────────────────────────
  function setupProgressObserver() {
    if (!D.me) return;
    let lastSent = null;
    let timer = null;
    const send = (paraId) => {
      const m = paraId.match(/^ch(\d+)s(\d+)$/);
      if (!m) return;
      const ch = parseInt(m[1], 10), sec = parseInt(m[2], 10);
      const key = `${ch}.${sec}`;
      if (key === lastSent) return;
      lastSent = key;
      D.postProgress(ch, sec);
    };
    const obs = new IntersectionObserver((entries) => {
      const visible = entries.filter(e => e.isIntersecting && e.intersectionRatio > 0.5);
      if (!visible.length) return;
      const para = visible[0].target;
      clearTimeout(timer);
      timer = setTimeout(() => send(para.id), 1500);
    }, { threshold: [0.5] });
    document.querySelectorAll('.para-section[id]').forEach(p => obs.observe(p));
  }

  // ─── Boot ────────────────────────────────────────────────────────
  async function boot() {
    repairStructureCards();
    await D.fetchMe();
    const [pub, mine] = await Promise.all([
      D.fetchPublicNotes(),
      D.fetchUserNotes(),
    ]);
    pub.forEach(renderSavedNote);
    mine.forEach(renderSavedNote);
    setupProgressObserver();
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
```

- [ ] **Step 3: Replace old annotate.js with a deprecation stub**

`static/annotate.js`:
```javascript
// Deprecated. Functionality moved into annotate-data.js + annotate-ui.js.
// Kept as an empty shim so cached HTML pages don't 404.
```

- [ ] **Step 4: Wire both new scripts in both HTML files**

In `/Users/ben/Downloads/belowiceberg/gatsby-teaching-edition.html` and `belowiceberg-website-v2.html`, find the line:
```html
<script src="/static/annotate.js" defer></script>
```
Replace with:
```html
<script src="/static/annotate-data.js" defer></script>
<script src="/static/annotate-ui.js" defer></script>
```

- [ ] **Step 5: Parse-check JS**

```bash
node --check /Users/ben/Downloads/belowiceberg/static/annotate-data.js
node --check /Users/ben/Downloads/belowiceberg/static/annotate-ui.js
```
Expected: both exit 0 silently.

- [ ] **Step 6: Add the bi-pop-scope CSS**

Append to `/Users/ben/Downloads/belowiceberg/static/annotate.css`:
```css
.bi-pop-scope {
  padding: 8px 14px;
  border-top: 1px solid #f0e9d8;
  font-size: 12px;
  color: var(--text2, #6b5e3e);
  display: flex; gap: 14px; align-items: center;
}
.bi-pop-scope label { display: inline-flex; gap: 6px; align-items: center; cursor: pointer; }
.bi-pop-scope input[type="radio"] { margin: 0; }
```

- [ ] **Step 7: Commit**

```bash
git add static/annotate-data.js static/annotate-ui.js static/annotate.js static/annotate.css gatsby-teaching-edition.html belowiceberg-website-v2.html
git commit -m "refactor(frontend): split annotate.js into data + ui layers; admin scope toggle; progress observer"
```

---

## Task 12: Library page (real wire)

**Files:**
- Create: `/Users/ben/Downloads/belowiceberg/library/index.html`
- Create: `/Users/ben/Downloads/belowiceberg/library/styles.css`

- [ ] **Step 1: Copy design's styles.css verbatim**

```bash
cp /tmp/design-fetch3/belowiceberg-design-system/project/library/styles.css /Users/ben/Downloads/belowiceberg/library/styles.css
```

(If `/tmp/design-fetch3` no longer exists, ask the user to re-share the design bundle and abort with a BLOCKED status.)

- [ ] **Step 2: Write library/index.html (HTML shell + JS wire)**

`/Users/ben/Downloads/belowiceberg/library/index.html`:
```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>B社 · 你的书房 · Library</title>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<nav class="lib-nav">
  <a href="/" class="lib-brand">
    <div class="seal"><span>B社</span></div>
    <span class="brand-en">BelowIceberg</span>
  </a>
  <ul class="lib-nav-links">
    <li><a href="/library" class="active">书房</a></li>
    <li><a href="/">书目</a></li>
    <li><a href="/settings">设置</a></li>
  </ul>
  <a href="#" id="lib-logout" class="lib-nav-cta">退出</a>
</nav>

<main class="lib-page">
  <div id="lib-loading" style="text-align:center;padding:80px 20px;color:#7a7466">加载中…</div>
  <div id="lib-root" hidden></div>
</main>

<script>
(async () => {
  const r = await fetch('/api/library', { credentials: 'same-origin' });
  if (r.status === 401) { location.href = '/login/?next=/library/'; return; }
  if (!r.ok) { document.getElementById('lib-loading').textContent = '加载失败'; return; }
  const data = await r.json();
  document.getElementById('lib-loading').remove();
  const root = document.getElementById('lib-root');
  root.hidden = false;

  // Continue reading
  const cur = data.current;
  const continueHtml = cur
    ? `<section class="lib-continue">
         <div class="lib-eyebrow">CONTINUE · 继续阅读</div>
         <h2 class="lib-cur-title">${escapeHtml(cur.book_slug.replace('gatsby','The Great Gatsby'))}</h2>
         <p class="lib-cur-pos">第 ${cur.chapter} 章 · 第 ${cur.section} 节</p>
         <a class="lib-cta" href="/${cur.book_slug}#ch${cur.chapter}s${cur.section}">继续阅读 →</a>
       </section>`
    : `<section class="lib-continue lib-empty">
         <p>你还没有开始阅读。<a href="/gatsby">从《了不起的盖茨比》开始 →</a></p>
       </section>`;

  // Stats
  const s = data.stats;
  const statsHtml = `
    <section class="lib-stats">
      <div><span class="num">${s.sessions}</span><span class="lbl">阅读天数</span></div>
      <div><span class="num">${s.streak_days}</span><span class="lbl">连续阅读</span></div>
      <div><span class="num">${data.all_my_notes.length}</span><span class="lbl">我的注解</span></div>
    </section>`;

  // Notes
  const byBook = {};
  for (const n of data.all_my_notes) (byBook[n.book_slug] ||= []).push(n);
  const notesHtml = Object.keys(byBook).length === 0
    ? `<section class="lib-notes lib-empty"><p>暂无注解。在书中选中文字后调用 AI 即可保存。</p></section>`
    : `<section class="lib-notes">
         <div class="lib-eyebrow">MY NOTES · 我的注解</div>
         ${Object.entries(byBook).map(([slug, list]) => `
           <h3 class="lib-notes-book">${escapeHtml(slug)}</h3>
           <ul class="lib-notes-list">
             ${list.map(n => `
               <li class="lib-note lib-note-${n.category}">
                 <span class="lib-note-cat">${({vocab:'词汇',grammar:'语法',structure:'句子结构'})[n.category]}</span>
                 <span class="lib-note-term">${escapeHtml(n.selectedText)}</span>
                 <div class="lib-note-body">${escapeHtml(n.responseMarkdown).slice(0,240)}${n.responseMarkdown.length > 240 ? '…' : ''}</div>
                 <a class="lib-note-src" href="/${slug}#${n.paraId}">跳转到原文 →</a>
               </li>`).join('')}
           </ul>`).join('')}
       </section>`;

  root.innerHTML = continueHtml + statsHtml + notesHtml;

  document.getElementById('lib-logout').onclick = async (e) => {
    e.preventDefault();
    await fetch('/api/auth/logout', { method:'POST', credentials:'same-origin' });
    location.href = '/';
  };
})();

function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
</script>
</body>
</html>
```

- [ ] **Step 3: Override library styles for the new structure**

Append to `/Users/ben/Downloads/belowiceberg/library/styles.css`:
```css
/* Overrides for the wired version */
body { margin: 0; font-family: 'Lora','Noto Serif SC',serif; background: #fafaf7; color: #2d2a20; }
.lib-nav { position: sticky; top: 0; height: 56px; display: flex; align-items: center; gap: 18px;
  padding: 0 32px; border-bottom: 0.5px solid rgba(184,148,46,0.25);
  background: rgba(250,250,247,0.92); backdrop-filter: blur(12px); z-index: 50; }
.lib-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; color: inherit; }
.lib-nav .seal { width: 30px; height: 30px; border: 1px solid #b8942e; transform: rotate(45deg);
  display: flex; align-items: center; justify-content: center; }
.lib-nav .seal span { font-family: 'Noto Serif SC',serif; font-size: 11px; color: #b8942e;
  transform: rotate(-45deg); letter-spacing: -0.02em; }
.lib-nav .brand-en { font-family: 'Playfair Display',serif; font-size: 17px; font-weight: 700; color: #1a1a15; }
.lib-nav-links { display: flex; gap: 4px; margin-left: 18px; list-style: none; padding: 0; }
.lib-nav-links a { font-family: 'Noto Serif SC',serif; font-size: 13px; color: #6b5e3e;
  padding: 5px 10px; border-radius: 4px; text-decoration: none; }
.lib-nav-links a.active { color: #b8942e; background: rgba(184,148,46,0.08); }
.lib-nav-cta { margin-left: auto; font-family: 'Noto Serif SC',serif; font-size: 12px;
  color: #6b5e3e; text-decoration: none; padding: 5px 10px; }
.lib-page { max-width: 760px; margin: 0 auto; padding: 48px 32px 80px; }
.lib-eyebrow { font-family: 'JetBrains Mono',monospace; font-size: 10px;
  letter-spacing: 0.25em; text-transform: uppercase; color: #b8942e; margin-bottom: 8px; }
.lib-continue { padding: 24px 0; border-bottom: 0.5px solid rgba(184,148,46,0.25); margin-bottom: 24px; }
.lib-cur-title { font-family: 'Playfair Display',serif; font-size: 28px; margin: 0 0 6px; }
.lib-cur-pos { font-family: 'Noto Serif SC',serif; color: #6b5e3e; margin: 0 0 16px; }
.lib-cta { display: inline-block; background: #b8942e; color: #fafaf7; padding: 8px 18px;
  border-radius: 4px; text-decoration: none; font-family: 'Noto Serif SC',serif; font-size: 13px; }
.lib-empty { color: #7a7466; font-style: italic; }
.lib-stats { display: flex; gap: 32px; padding: 20px 0; border-bottom: 0.5px solid rgba(184,148,46,0.25); margin-bottom: 24px; }
.lib-stats > div { display: flex; flex-direction: column; }
.lib-stats .num { font-family: 'Playfair Display',serif; font-size: 32px; font-weight: 700; color: #1a1a15; }
.lib-stats .lbl { font-family: 'Noto Serif SC',serif; font-size: 12px; color: #6b5e3e; }
.lib-notes-book { font-family: 'Playfair Display',serif; font-size: 16px; margin: 24px 0 8px; color: #1a1a15; }
.lib-notes-list { list-style: none; padding: 0; margin: 0; }
.lib-note { padding: 12px 14px; border-left: 3px solid #b8942e; background: #f7f3e9;
  margin-bottom: 10px; border-radius: 0 4px 4px 0; }
.lib-note-vocab { border-left-color: #3a7bb5; }
.lib-note-grammar { border-left-color: #3a8b5e; }
.lib-note-structure { border-left-color: #7a4f9b; }
.lib-note-cat { font-family: 'JetBrains Mono',monospace; font-size: 10px;
  background: #1a1a15; color: #fafaf7; padding: 2px 6px; border-radius: 3px; margin-right: 8px; }
.lib-note-term { font-family: 'Lora',serif; font-weight: 600; color: #1a1a15; }
.lib-note-body { margin: 6px 0; color: #2d2a20; font-size: 14px; }
.lib-note-src { font-family: 'Noto Serif SC',serif; font-size: 11px; color: #6b5e3e; text-decoration: none; }
.lib-note-src:hover { color: #b8942e; }
```

- [ ] **Step 4: Commit**

```bash
git add library/
git commit -m "feat(library): wire /library/ to /api/library (continue reading, stats, my notes)"
```

---

## Task 13: Login page — replace OAuth mock with real form

**Files:**
- Modify: `/Users/ben/Downloads/belowiceberg/login/index.html`

- [ ] **Step 1: Read the current login/index.html**

```bash
wc -l /Users/ben/Downloads/belowiceberg/login/index.html
```

Note the line where `<OAuthButtons screen={screen} />` is rendered in BOTH the mobile and desktop branches of `VariationB`. There are two occurrences (one per branch).

- [ ] **Step 2: Replace the OAuth blocks with a real form, twice**

For the **desktop** branch (search for `<OAuthButtons screen={screen} />` inside the `// desktop: 50/50 split` block, but NOT inside the `forgot` conditional), replace:
```jsx
<OAuthButtons screen={screen} />
<div className="lg-or" style={{ margin: '8px 0' }}>OR · 或</div>
<a className="lg-link" style={{ alignSelf: 'flex-start' }}>用邮箱链接登录 →</a>
{screen === 'login' && (
  <a className="lg-link" style={{ alignSelf: 'flex-start', fontSize: 12, color: 'var(--text3)' }} onClick={() => { history.pushState({},'','?screen=forgot'); window.dispatchEvent(new Event('popstate')); }}>
    无法登录？
  </a>
)}
```
with:
```jsx
<EmailForm screen={screen} />
<div className="lg-or" style={{ margin: '8px 0', fontSize: 11 }}>OR · 或</div>
<button className="lg-btn lg-btn-disabled" disabled title="即将上线">用 Apple {screen === 'signup' ? '注册' : '登录'}</button>
<button className="lg-btn lg-btn-disabled" disabled title="即将上线">用 Google {screen === 'signup' ? '注册' : '登录'}</button>
```

For the **mobile** branch (inside `if (isMobile)`), replace the corresponding `OAuthButtons` + email-link line with the same `<EmailForm screen={screen} />` (no "OR" separator on mobile).

- [ ] **Step 3: Insert the EmailForm component**

Insert immediately above `const VariationB = ...`:
```jsx
const EmailForm = ({ screen }) => {
  const [email, setEmail] = React.useState('');
  const [pw, setPw] = React.useState('');
  const [name, setName] = React.useState('');
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    const body = screen === 'signup'
      ? { email, password: pw, display_name: name }
      : { email, password: pw };
    const url = screen === 'signup' ? '/api/auth/signup' : '/api/auth/login';
    try {
      const r = await fetch(url, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setErr(j.detail || `HTTP ${r.status}`);
        setBusy(false);
        return;
      }
      const next = new URLSearchParams(location.search).get('next') || '/library/';
      location.href = next;
    } catch (ex) {
      setErr(ex.message); setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <input type="email" required placeholder="邮箱" value={email}
             onChange={e => setEmail(e.target.value)} className="lg-input" autoComplete="email" />
      {screen === 'signup' && (
        <input type="text" required placeholder="显示名" value={name}
               onChange={e => setName(e.target.value)} className="lg-input" autoComplete="name" />
      )}
      <input type="password" required placeholder={screen === 'signup' ? '密码 (8+ 字符)' : '密码'}
             minLength={screen === 'signup' ? 8 : undefined}
             value={pw} onChange={e => setPw(e.target.value)} className="lg-input"
             autoComplete={screen === 'signup' ? 'new-password' : 'current-password'} />
      {err && <div className="lg-err">{err}</div>}
      <button type="submit" className="lg-btn lg-btn-primary" disabled={busy}>
        {busy ? '…' : (screen === 'signup' ? '注册' : '登录')}
      </button>
    </form>
  );
};
```

- [ ] **Step 4: Add input + button styles**

Append to `/Users/ben/Downloads/belowiceberg/login/styles.css`:
```css
.lg-input {
  font-family: 'Noto Serif SC','Lora',serif;
  font-size: 14px;
  padding: 10px 12px;
  border: 1px solid var(--border, rgba(184,148,46,0.25));
  border-radius: 4px;
  background: #fff;
  color: #1a1a15;
  outline: none;
}
.lg-input:focus { border-color: var(--gold, #b8942e); }
.lg-btn-primary {
  background: var(--gold, #b8942e); color: #fafaf7; border: none;
  padding: 10px 14px; border-radius: 4px; font-family: 'Noto Serif SC',serif;
  font-size: 14px; cursor: pointer;
}
.lg-btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.lg-btn-disabled {
  background: #f0eee9; color: #a89870; border: 1px solid var(--border, rgba(184,148,46,0.25));
  padding: 8px 12px; border-radius: 4px; font-family: 'Noto Serif SC',serif;
  font-size: 13px; cursor: not-allowed;
}
.lg-err {
  background: rgba(196,90,58,0.08); color: #c45a3a;
  border-left: 2px solid #c45a3a; padding: 6px 10px; font-size: 12.5px;
  font-family: 'Noto Serif SC',serif;
}
```

- [ ] **Step 5: Commit**

```bash
git add login/
git commit -m "feat(login): wire real email+password form; disable OAuth buttons with 即将上线"
```

---

## Task 14: Settings page wiring

**Files:**
- Modify: `/Users/ben/Downloads/belowiceberg/settings/index.html`

- [ ] **Step 1: Read the current settings/index.html**

The current file is the deployed mock — hardcoded `USER`, no API calls. We need to: keep all sections visible, but wire display_name + change_password + cards_open_default + clear_progress + logout.

- [ ] **Step 2: Replace the hardcoded USER with a live fetch + add wired handlers**

Open `/Users/ben/Downloads/belowiceberg/settings/index.html`. Find the line:
```javascript
const USER = {
  name: '林清岚', initials: 'L', email: 'qinglan.lin@example.com',
  joined: '2026 年 3 月', balance: 580,
};
```

Replace it with a hook that fetches `/api/me` and shows the page; if 401, redirect to `/login?next=/settings/`. Insert above the existing `App` component:

```jsx
const useMe = () => {
  const [me, setMe] = React.useState(null);
  const [loaded, setLoaded] = React.useState(false);
  React.useEffect(() => {
    fetch('/api/me', { credentials: 'same-origin' })
      .then(r => { if (r.status === 401) { location.href = '/login/?next=/settings/'; return null; } return r.json(); })
      .then(data => { if (data) { setMe(data); setLoaded(true); } });
  }, []);
  return { me, setMe, loaded };
};

const patchMe = async (patch) => {
  const r = await fetch('/api/me', {
    method: 'PATCH', credentials: 'same-origin',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(patch),
  });
  return r.ok;
};
```

Then in the `App` component (or wherever USER is consumed), replace references to `USER.name` / `USER.email` with `me.display_name` / `me.email`. Where the file references `USER.balance` etc, leave those as visual placeholders — those token fields stay un-wired per spec.

If `App` is small enough, the simplest path: wrap its return in `{ loaded ? <Page user={me} setMe={setMe} /> : <div>加载中…</div> }` where `Page` is the existing content.

Add these wired handlers inline where the corresponding UI lives:

```jsx
// Display name field (find the existing input in section 一 · 账户 and replace)
<input className="st-input" defaultValue={me.display_name}
  onBlur={async (e) => {
    const v = e.target.value.trim();
    if (v && v !== me.display_name) { if (await patchMe({display_name: v})) setMe({...me, display_name: v}); }
  }} />

// Change-password button — opens an inline panel
const [pwOpen, setPwOpen] = React.useState(false);
const [pwCur, setPwCur] = React.useState(''); const [pwNew, setPwNew] = React.useState('');
const [pwErr, setPwErr] = React.useState('');
const submitPw = async (e) => {
  e.preventDefault(); setPwErr('');
  const r = await fetch('/api/me/change-password', {
    method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({current: pwCur, new: pwNew}),
  });
  if (r.ok) { setPwOpen(false); setPwCur(''); setPwNew(''); alert('密码已更新'); }
  else { const j = await r.json().catch(()=>({})); setPwErr(j.detail || '失败'); }
};
// In the Account section, render:
<button className="st-btn" onClick={() => setPwOpen(!pwOpen)}>修改密码</button>
{pwOpen && (
  <form onSubmit={submitPw} style={{display:'flex',flexDirection:'column',gap:8,marginTop:8}}>
    <input type="password" placeholder="当前密码" value={pwCur} onChange={e=>setPwCur(e.target.value)} required className="st-input"/>
    <input type="password" placeholder="新密码 (8+ 字符)" value={pwNew} onChange={e=>setPwNew(e.target.value)} required minLength={8} className="st-input"/>
    {pwErr && <div className="st-err">{pwErr}</div>}
    <button type="submit" className="st-btn st-btn-primary">确认</button>
  </form>
)}

// Cards-open-by-default toggle (section 三 · 注解)
<label className="st-toggle">
  <input type="checkbox" checked={!!me.cards_open_default}
    onChange={async (e) => {
      if (await patchMe({cards_open_default: e.target.checked})) setMe({...me, cards_open_default: e.target.checked});
    }} />
  <span>注解卡片默认展开</span>
</label>

// 清除阅读进度 button (section 四)
<button className="st-btn st-btn-danger" onClick={async () => {
  if (!confirm('确认清除所有阅读进度？此操作不可撤销。')) return;
  const r = await fetch('/api/me/clear-progress', { method:'POST', credentials:'same-origin' });
  if (r.ok) alert('阅读进度已清除'); else alert('失败');
}}>清除阅读进度</button>

// 退出登录
<button className="st-btn" onClick={async () => {
  await fetch('/api/auth/logout', { method:'POST', credentials:'same-origin' });
  location.href = '/';
}}>退出登录</button>
```

For sections marked visual-only (tokens, change email, delete account, visible categories filter): leave existing markup but add the attribute `disabled` to any inputs/buttons and `data-v1-disabled="true"` so a CSS rule can grey them.

- [ ] **Step 3: Add settings styles for the wired controls**

Append to `/Users/ben/Downloads/belowiceberg/settings/styles.css`:
```css
.st-input { font-family: 'Noto Serif SC','Lora',serif; font-size: 14px; padding: 8px 10px;
  border: 1px solid rgba(184,148,46,0.25); border-radius: 4px; background: #fff; color: #1a1a15; outline: none; }
.st-input:focus { border-color: #b8942e; }
.st-btn { font-family: 'Noto Serif SC',serif; font-size: 13px; padding: 7px 14px;
  background: #fff; color: #2d2a20; border: 1px solid rgba(184,148,46,0.25);
  border-radius: 4px; cursor: pointer; }
.st-btn:hover { background: rgba(184,148,46,0.08); }
.st-btn-primary { background: #b8942e; color: #fafaf7; border-color: #b8942e; }
.st-btn-danger { color: #c45a3a; border-color: rgba(196,90,58,0.4); }
.st-btn-danger:hover { background: rgba(196,90,58,0.08); }
.st-err { background: rgba(196,90,58,0.08); color: #c45a3a; border-left: 2px solid #c45a3a;
  padding: 6px 10px; font-size: 12.5px; }
.st-toggle { display: inline-flex; gap: 8px; align-items: center; font-size: 13px;
  font-family: 'Noto Serif SC',serif; color: #2d2a20; }
[data-v1-disabled="true"] { opacity: 0.5; pointer-events: none; }
[data-v1-disabled="true"]::after { content: " (即将上线)"; font-size: 11px; color: #a89870; }
```

- [ ] **Step 4: Commit**

```bash
git add settings/
git commit -m "feat(settings): wire display_name, password change, cards_open, clear_progress, logout"
```

---

## Task 15: Deploy to Vultr + seed admin + smoke test

Operational task. The expect-based SSH helpers from earlier sessions are in `/tmp/ssh_run.exp` and `/tmp/scp_run.exp` — recreate them if absent. SSH password is in the user's notes.

**Files:** none (operational)

- [ ] **Step 1: Run full test suite locally**

```bash
cd /Users/ben/Downloads/belowiceberg/server
.venv/bin/pytest -v
```
Expected: all tests pass across `test_db, test_users, test_user_notes, test_progress, test_auth, test_routes_auth, test_routes_user_notes, test_routes_progress, test_routes, test_notes, test_config, test_deepseek`.

- [ ] **Step 2: Rsync repo to server**

If `/tmp/ssh_run.exp` doesn't exist, recreate it:
```bash
cat > /tmp/ssh_run.exp << 'EOF'
#!/usr/bin/expect -f
set timeout 60
set pw [lindex $argv 0]
set cmd [lindex $argv 1]
spawn ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@66.135.16.106 $cmd
expect { "password:" { send "$pw\r"; exp_continue } eof }
EOF
chmod +x /tmp/ssh_run.exp
```

Then rsync:
```bash
expect -c '
set timeout 120
spawn rsync -avz --delete --exclude ".venv" --exclude "__pycache__" --exclude ".pytest_cache" --exclude "*.egg-info" --exclude ".git" -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" /Users/ben/Downloads/belowiceberg/ root@66.135.16.106:/opt/belowiceberg/
expect "password:"; send "<PASSWORD>\r"; expect eof
'
```
Replace `<PASSWORD>` with the server root password before running.

- [ ] **Step 3: Install dependencies and run migrations**

```bash
/tmp/ssh_run.exp '<PASSWORD>' 'cd /opt/belowiceberg/server && .venv/bin/pip install -e ".[dev]" 2>&1 | tail -10'
/tmp/ssh_run.exp '<PASSWORD>' 'systemctl restart belowiceberg-api.service && sleep 2 && systemctl status belowiceberg-api.service --no-pager | head -12'
```
Expected: service active and running. Migrations apply on startup via `create_app()`.

- [ ] **Step 4: Sync deployed static + HTML files**

```bash
expect -c '
set timeout 60
spawn scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /Users/ben/Downloads/belowiceberg/static/annotate-data.js /Users/ben/Downloads/belowiceberg/static/annotate-ui.js /Users/ben/Downloads/belowiceberg/static/annotate.js /Users/ben/Downloads/belowiceberg/static/annotate.css root@66.135.16.106:/opt/belowiceberg/static/
expect "password:"; send "<PASSWORD>\r"; expect eof
'
expect -c '
set timeout 60
spawn scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /Users/ben/Downloads/belowiceberg/gatsby-teaching-edition.html /Users/ben/Downloads/belowiceberg/belowiceberg-website-v2.html root@66.135.16.106:/var/www/belowiceberg/
expect "password:"; send "<PASSWORD>\r"; expect eof
'
/tmp/ssh_run.exp '<PASSWORD>' 'mv /var/www/belowiceberg/belowiceberg-website-v2.html /var/www/belowiceberg/index.html; mv /var/www/belowiceberg/gatsby-teaching-edition.html /var/www/belowiceberg/gatsby.html'
```

Sync library/ and settings/ too:
```bash
/tmp/ssh_run.exp '<PASSWORD>' 'mkdir -p /var/www/belowiceberg/library /var/www/belowiceberg/settings'
expect -c '
set timeout 60
spawn scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /Users/ben/Downloads/belowiceberg/library/index.html /Users/ben/Downloads/belowiceberg/library/styles.css root@66.135.16.106:/var/www/belowiceberg/library/
expect "password:"; send "<PASSWORD>\r"; expect eof
'
expect -c '
set timeout 60
spawn scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /Users/ben/Downloads/belowiceberg/settings/index.html /Users/ben/Downloads/belowiceberg/settings/styles.css root@66.135.16.106:/var/www/belowiceberg/settings/
expect "password:"; send "<PASSWORD>\r"; expect eof
'
expect -c '
set timeout 60
spawn scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /Users/ben/Downloads/belowiceberg/login/index.html /Users/ben/Downloads/belowiceberg/login/styles.css root@66.135.16.106:/var/www/belowiceberg/login/
expect "password:"; send "<PASSWORD>\r"; expect eof
'
```

- [ ] **Step 5: Seed the admin user**

```bash
/tmp/ssh_run.exp '<PASSWORD>' 'cd /opt/belowiceberg/server && .venv/bin/python -m app.cli.create_admin'
```

This is interactive — the script prompts for email, display name, password, confirm. Use a real admin email and a fresh strong password (not `999999`). On success it prints `Created user 1 (...) as admin.`.

If you can't drive interactive prompts over the helper, instead use:
```bash
/tmp/ssh_run.exp '<PASSWORD>' "cd /opt/belowiceberg/server && BELOWICEBERG_DATA_DIR=/var/www/belowiceberg-data ADMIN_PASSWORD_HASH=ignored SESSION_SECRET=ignored DEEPSEEK_API_KEY=ignored .venv/bin/python -c \"from app.db import migrate; from app.users import create_user; migrate(); print(create_user('admin@belowiceberg.com', 'CHANGEME_strong_pw', 'Admin', is_admin=True))\""
```
Replace the email and password. Note: in v1 the service env file already has SESSION_SECRET/DEEPSEEK_API_KEY/BELOWICEBERG_DATA_DIR — the inline assignment above is for one-off scripting.

- [ ] **Step 6: Smoke-test endpoints**

```bash
# anonymous
curl -s -o /dev/null -w 'gatsby (anon): %{http_code}\n' http://66.135.16.106/gatsby
curl -s -o /dev/null -w '/api/me (anon): %{http_code}\n' http://66.135.16.106/api/me
curl -s -o /dev/null -w '/api/library (anon): %{http_code}\n' http://66.135.16.106/api/library

# signup new test user
curl -s -i -c /tmp/cookies.txt -X POST http://66.135.16.106/api/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@b.com","password":"smokepw123","display_name":"Smoke"}'

# /api/me with cookie
curl -s -b /tmp/cookies.txt http://66.135.16.106/api/me

# post a user note
curl -s -b /tmp/cookies.txt -X POST http://66.135.16.106/api/user-notes/gatsby \
  -H 'Content-Type: application/json' \
  -d '{"paraId":"ch1s1","category":"vocab","selectedText":"advice","responseMarkdown":"**advice** - 建议"}'

# fetch library
curl -s -b /tmp/cookies.txt http://66.135.16.106/api/library
```
Expected: gatsby=200, anon /api/me=401, anon /api/library=401, signup=200 with Set-Cookie, /api/me returns the smoke user, POST user-notes returns `{"ok":true,"id":1}`, /api/library returns json with one note.

- [ ] **Step 7: Delete the smoke user**

```bash
/tmp/ssh_run.exp '<PASSWORD>' "cd /opt/belowiceberg/server && BELOWICEBERG_DATA_DIR=/var/www/belowiceberg-data ADMIN_PASSWORD_HASH=ignored SESSION_SECRET=ignored DEEPSEEK_API_KEY=ignored .venv/bin/python -c \"from app.users import get_by_email, delete_user; u = get_by_email('smoke@b.com'); delete_user(u['id']) if u else None\""
```

- [ ] **Step 8: Commit empty deploy marker**

```bash
cd /Users/ben/Downloads/belowiceberg
git commit --allow-empty -m "deploy: user accounts v1 rolled out to 66.135.16.106"
git push origin main
```

---

## Task 16: Manual e2e in the browser

**Files:** none

- [ ] **Step 1: Sign up a real user**

In an incognito window: go to http://66.135.16.106/login/?screen=signup → enter an email + 8+ char password + display name → click 注册. Expected: redirected to `/library/`.

- [ ] **Step 2: Read a chapter, watch progress**

Open `/gatsby`. Scroll into Ch.3. Wait 2 seconds. Check `/api/progress`-effect: open browser DevTools → Network tab → should see a POST to `/api/progress` with `{book_slug:"gatsby", chapter:3, section:N}`.

- [ ] **Step 3: Use AI selection**

In `/gatsby`, select a word. The dark selection bar should appear. Click 词汇. Popover streams response. Save → popover closes, a new card with the selected term as the title appears in that paragraph. There should be NO "保存到个人 / 发布到所有读者" toggle — you're not admin.

- [ ] **Step 4: Visit library**

Go to `/library/`. Expected:
- "Continue reading" shows the chapter/section your progress observer saved.
- "我的注解" shows the note you saved in Step 3.
- Stats show 1 session, 1 streak day, 1 note.

- [ ] **Step 5: Visit settings**

Go to `/settings/`. Expected:
- Account section shows your email + editable display name.
- Edit display name → blur → reload → name persists.
- 修改密码 button opens form; change password works.
- Cards-open-by-default toggle persists across reload.
- 清除阅读进度 → after confirm, library shows no current book.
- 退出登录 → redirected to `/`, /api/me returns 401.

- [ ] **Step 6: Log in as admin**

Sign in with the admin email seeded in Task 15. Open `/gatsby`. Select text → click 词汇. Popover now shows "保存到个人 / 发布到所有读者" radios. Pick 发布 → save. Open `/gatsby` in an incognito window (anonymous) — the new annotation should appear publicly.

- [ ] **Step 7: Commit a verification marker**

```bash
cd /Users/ben/Downloads/belowiceberg
git commit --allow-empty -m "verify: user accounts v1 e2e smoke passed in browser"
git push origin main
```

---

## Self-Review Notes (for the implementer)

If anything in this plan turns out wrong during implementation, the spec is the source of truth: `docs/superpowers/specs/2026-05-24-user-accounts-design.md`.

Likely friction points:
- **pydantic EmailStr** requires `email-validator` (added in Task 4 Step 5). Tests will fail with "email-validator is not installed" if pip install is skipped.
- **IntersectionObserver in JS** doesn't fire if the page is fully scrolled past on load. That's fine — progress will fire on the next scroll.
- **The `db` fixture uses `reset_conn()`** — if any module caches its own conn separate from `db.py`, that module would see a stale connection. Don't add caching outside `db.py`.
- **Old admin login (`POST /admin/login`)** still works during the migration window since we left `routes/admin.py` registered. Remove it in a follow-up commit after you've verified the new flow works for both you (admin) and a regular user.
- **The settings page** uses Babel-in-browser React. Edits to its JSX won't show until you scp the new HTML and hard-reload (the file is parsed client-side each load — no build step).
