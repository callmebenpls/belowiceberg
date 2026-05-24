# Annotation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin-only annotation system that lets the logged-in admin select text on a teaching-edition page, ask DeepSeek to analyze it under 词汇/语法/句子结构, and save the response into the matching subsection of the paragraph's card — visible to all future readers.

**Architecture:** FastAPI app on `127.0.0.1:8001` (systemd) behind nginx, JSON sidecar files at `/var/www/belowiceberg-data/notes/<book>.json` as source of truth, vanilla-JS `annotate.js` script added to each teaching-edition page. No build step, no database.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, httpx, itsdangerous, bcrypt, pytest. Vanilla JS + CSS for frontend. nginx for proxy. systemd for process supervision. DeepSeek chat completions API for analysis.

**Spec:** `docs/superpowers/specs/2026-05-23-annotation-system-design.md`

---

## File Structure

Repo root: `/Users/ben/Downloads/belowiceberg/`

```
belowiceberg/
├── belowiceberg-website-v2.html          (existing — modified in Task 12)
├── gatsby-teaching-edition.html          (existing — modified in Task 12)
├── server/                                (NEW — Python backend)
│   ├── pyproject.toml
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app factory
│   │   ├── config.py                     # env loading
│   │   ├── auth.py                       # password check, session cookies, dependency
│   │   ├── notes.py                      # sidecar read/write
│   │   ├── deepseek.py                   # DeepSeek streaming client
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── admin.py                  # /admin/login, /admin/logout, /admin
│   │       ├── notes.py                  # GET/POST /api/notes/<slug>
│   │       └── query.py                  # POST /api/query (SSE)
│   ├── prompts/
│   │   ├── vocab.txt
│   │   ├── grammar.txt
│   │   └── structure.txt
│   └── tests/
│       ├── conftest.py
│       ├── test_config.py
│       ├── test_notes.py
│       ├── test_auth.py
│       ├── test_deepseek.py
│       └── test_routes.py
├── static/                                (NEW — served by nginx at /static/)
│   ├── annotate.js
│   └── annotate.css
└── deploy/                                (NEW — server config)
    ├── belowiceberg-api.service
    ├── nginx-belowiceberg.conf
    └── install.sh
```

**Boundaries:**
- `notes.py` knows nothing about HTTP — pure file I/O on the sidecar JSON.
- `deepseek.py` knows nothing about FastAPI — just an async generator that yields tokens.
- `auth.py` produces/validates cookies; routes apply it as a `Depends()`.
- Frontend `annotate.js` is the only file that touches the DOM.

---

## Task 0: Project scaffold

**Files:**
- Create: `/Users/ben/Downloads/belowiceberg/.gitignore`
- Create: `/Users/ben/Downloads/belowiceberg/server/pyproject.toml`
- Create: `/Users/ben/Downloads/belowiceberg/server/app/__init__.py` (empty)
- Create: `/Users/ben/Downloads/belowiceberg/server/app/routes/__init__.py` (empty)
- Create: `/Users/ben/Downloads/belowiceberg/server/tests/__init__.py` (empty)
- Create: `/Users/ben/Downloads/belowiceberg/server/tests/conftest.py`

- [ ] **Step 1: Init git repo**

```bash
cd /Users/ben/Downloads/belowiceberg
git init -b main
```

- [ ] **Step 2: Write .gitignore**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.env
*.db
node_modules/
.DS_Store
```

- [ ] **Step 3: Write pyproject.toml**

```toml
[project]
name = "belowiceberg-server"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi==0.115.*",
  "uvicorn[standard]==0.32.*",
  "httpx==0.27.*",
  "itsdangerous==2.2.*",
  "bcrypt==4.2.*",
  "python-multipart==0.0.12",
]

[project.optional-dependencies]
dev = [
  "pytest==8.3.*",
  "pytest-asyncio==0.24.*",
  "pytest-httpx==0.32.*",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Create venv and install**

```bash
cd /Users/ben/Downloads/belowiceberg/server
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 5: Write conftest.py**

```python
# server/tests/conftest.py
import os
import pytest
from pathlib import Path

@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Isolated data dir per test."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    monkeypatch.setenv("BELOWICEBERG_DATA_DIR", str(tmp_path))
    return tmp_path

@pytest.fixture
def env(monkeypatch, tmp_data_dir):
    """Sane test env."""
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$KIXxPfnK4TBnXcGmZ7eOe.dxZBT9YR/qK1pT4yL.zJtBM3oWzqJ0a")  # bcrypt of "test"
    monkeypatch.setenv("SESSION_SECRET", "test-secret-do-not-use-in-prod")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return tmp_data_dir
```

- [ ] **Step 6: Verify scaffold**

```bash
cd /Users/ben/Downloads/belowiceberg/server
.venv/bin/pytest --collect-only
```
Expected: `collected 0 items` (no tests yet, but no errors).

- [ ] **Step 7: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add .gitignore server/
git commit -m "scaffold: init server package with deps and pytest config"
```

---

## Task 1: Config loader

Loads required env vars at startup, fails loudly if missing. Single source of truth for paths and secrets.

**Files:**
- Create: `server/app/config.py`
- Create: `server/tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# server/tests/test_config.py
import pytest
from pathlib import Path
from app.config import load_config, ConfigError

def test_load_config_reads_env(env):
    cfg = load_config()
    assert cfg.admin_password_hash.startswith("$2b$")
    assert cfg.session_secret == "test-secret-do-not-use-in-prod"
    assert cfg.deepseek_api_key == "sk-test"
    assert cfg.notes_dir == Path(env) / "notes"

def test_load_config_raises_when_missing(monkeypatch):
    for var in ["ADMIN_PASSWORD_HASH", "SESSION_SECRET", "DEEPSEEK_API_KEY"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BELOWICEBERG_DATA_DIR", "/tmp/x")
    with pytest.raises(ConfigError):
        load_config()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ben/Downloads/belowiceberg/server
.venv/bin/pytest tests/test_config.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Implement config.py**

```python
# server/app/config.py
import os
from dataclasses import dataclass
from pathlib import Path

class ConfigError(RuntimeError):
    pass

@dataclass(frozen=True)
class Config:
    admin_password_hash: str
    session_secret: str
    deepseek_api_key: str
    data_dir: Path
    notes_dir: Path

def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise ConfigError(f"Missing required env var: {name}")
    return v

def load_config() -> Config:
    data_dir = Path(_require("BELOWICEBERG_DATA_DIR"))
    return Config(
        admin_password_hash=_require("ADMIN_PASSWORD_HASH"),
        session_secret=_require("SESSION_SECRET"),
        deepseek_api_key=_require("DEEPSEEK_API_KEY"),
        data_dir=data_dir,
        notes_dir=data_dir / "notes",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_config.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add server/app/config.py server/tests/test_config.py
git commit -m "feat(config): load required env vars with explicit failures"
```

---

## Task 2: Notes storage (atomic sidecar I/O)

Pure file I/O for `<slug>.json`. Atomic write via tmp+rename. Slug whitelist to prevent path traversal.

**Files:**
- Create: `server/app/notes.py`
- Create: `server/tests/test_notes.py`

- [ ] **Step 1: Write failing tests**

```python
# server/tests/test_notes.py
import json
import pytest
from pathlib import Path
from app.notes import read_notes, append_note, NoteValidationError, Note

def test_read_notes_returns_empty_when_no_file(env):
    assert read_notes("gatsby") == []

def test_append_then_read(env):
    note = Note(
        paraId="para3",
        category="vocab",
        selectedText="advantages",
        responseMarkdown="**advantages** — 优势",
    )
    append_note("gatsby", note)
    notes = read_notes("gatsby")
    assert len(notes) == 1
    assert notes[0].selectedText == "advantages"
    assert notes[0].createdAt  # auto-set

def test_append_multiple_preserves_order(env):
    for s in ["a", "b", "c"]:
        append_note("gatsby", Note(paraId="p1", category="vocab",
                                   selectedText=s, responseMarkdown=s))
    notes = read_notes("gatsby")
    assert [n.selectedText for n in notes] == ["a", "b", "c"]

def test_slug_traversal_rejected(env):
    with pytest.raises(NoteValidationError):
        read_notes("../etc/passwd")
    with pytest.raises(NoteValidationError):
        append_note("../x", Note(paraId="p", category="vocab",
                                  selectedText="t", responseMarkdown="r"))

def test_bad_category_rejected(env):
    with pytest.raises(NoteValidationError):
        append_note("gatsby", Note(paraId="p1", category="bogus",
                                    selectedText="x", responseMarkdown="y"))

def test_atomic_write_no_tmp_leftover(env):
    append_note("gatsby", Note(paraId="p", category="vocab",
                                selectedText="x", responseMarkdown="y"))
    leftovers = list(env.glob("notes/*.tmp"))
    assert leftovers == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_notes.py -v
```
Expected: all FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement notes.py**

```python
# server/app/notes.py
import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from app.config import load_config

VALID_CATEGORIES = {"vocab", "grammar", "structure"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

class NoteValidationError(ValueError):
    pass

@dataclass
class Note:
    paraId: str
    category: str
    selectedText: str
    responseMarkdown: str
    createdAt: str = ""

def _validate_slug(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise NoteValidationError(f"Invalid book slug: {slug!r}")

def _validate_note(n: Note) -> None:
    if n.category not in VALID_CATEGORIES:
        raise NoteValidationError(f"Invalid category: {n.category!r}")
    if not n.paraId or not n.selectedText or not n.responseMarkdown:
        raise NoteValidationError("paraId, selectedText, responseMarkdown required")
    if len(n.selectedText) > 2000 or len(n.responseMarkdown) > 8000:
        raise NoteValidationError("field too long")

def _path_for(slug: str) -> Path:
    _validate_slug(slug)
    cfg = load_config()
    cfg.notes_dir.mkdir(parents=True, exist_ok=True)
    return cfg.notes_dir / f"{slug}.json"

def read_notes(slug: str) -> list[Note]:
    p = _path_for(slug)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Note(**n) for n in data]

def append_note(slug: str, note: Note) -> None:
    _validate_note(note)
    if not note.createdAt:
        note.createdAt = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = _path_for(slug)
    existing = read_notes(slug)
    existing.append(note)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps([asdict(n) for n in existing], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, p)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_notes.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add server/app/notes.py server/tests/test_notes.py
git commit -m "feat(notes): atomic JSON sidecar storage with slug+field validation"
```

---

## Task 3: Auth (password check + signed cookies)

bcrypt password verification and `itsdangerous` signed session cookie. FastAPI dependency `require_admin` for route protection.

**Files:**
- Create: `server/app/auth.py`
- Create: `server/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# server/tests/test_auth.py
import pytest
from app.auth import verify_password, issue_session, validate_session

def test_verify_password_correct(env):
    # hash in conftest is bcrypt("test")
    assert verify_password("test") is True

def test_verify_password_wrong(env):
    assert verify_password("nope") is False

def test_issue_and_validate_roundtrip(env):
    token = issue_session()
    assert validate_session(token) is True

def test_validate_session_rejects_tampered(env):
    token = issue_session()
    bad = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert validate_session(bad) is False

def test_validate_session_rejects_empty(env):
    assert validate_session("") is False
    assert validate_session(None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_auth.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement auth.py**

```python
# server/app/auth.py
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Cookie, HTTPException, status
from app.config import load_config

SESSION_COOKIE = "belowiceberg_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
_SALT = "belowiceberg-session-v1"

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(load_config().session_secret, salt=_SALT)

def verify_password(password: str) -> bool:
    cfg = load_config()
    try:
        return bcrypt.checkpw(password.encode("utf-8"),
                              cfg.admin_password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False

def issue_session() -> str:
    return _serializer().dumps({"role": "admin"})

def validate_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
        return data.get("role") == "admin"
    except (BadSignature, SignatureExpired):
        return False

def require_admin(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> None:
    """FastAPI dependency."""
    if not validate_session(session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="admin login required")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_auth.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add server/app/auth.py server/tests/test_auth.py
git commit -m "feat(auth): bcrypt password check and signed session cookie"
```

---

## Task 4: DeepSeek streaming client

Async generator that yields response tokens. Pluggable httpx client for testing. Loads category prompts from `server/prompts/`.

**Files:**
- Create: `server/app/deepseek.py`
- Create: `server/prompts/vocab.txt`
- Create: `server/prompts/grammar.txt`
- Create: `server/prompts/structure.txt`
- Create: `server/tests/test_deepseek.py`

- [ ] **Step 1: Write the three prompt files**

`server/prompts/vocab.txt`:
```
你是一个为中国英语学习者服务的词汇分析助手。用户会选中一个英文单词或短语，并提供它所在段落的完整原文作为上下文。

请按以下格式回复（全部使用简体中文，控制在150字以内）：

**[原词]** /国际音标/ — 含义解释。

如有必要，补充1-2句关于该词在此具体上下文中的细微含义、词性、固定搭配，或学习者常犯的错误。

不要重复用户的提问。不要加任何前言或寒暄。直接输出注解。
```

`server/prompts/grammar.txt`:
```
你是一个为中国英语学习者服务的语法分析助手。用户会选中一段英文（通常是一个词、短语或半个句子），并提供完整段落原文作为上下文。

请用简体中文，控制在150字以内，分析此处涉及的关键语法点：时态、语态、虚拟语气、从句类型、非谓语动词、倒装、强调、省略等。指出中国学生在这个语法点上常犯的错误。

不要重复用户的提问。不要加前言。直接输出语法解析。
```

`server/prompts/structure.txt`:
```
你是一个为中国英语学习者服务的句子结构分析助手。用户会选中一个英文句子或子句，并提供完整段落原文作为上下文。

请用简体中文，控制在200字以内，按"主语 / 动作 / 宾语或补语 / 修饰语依附"的层次拆解所选句子的结构。如果句子较长，按阅读顺序从前到后展开主干与修饰成分。

不要重复用户的提问。不要加前言。直接输出结构分析。
```

- [ ] **Step 2: Write failing tests**

```python
# server/tests/test_deepseek.py
import pytest
from app.deepseek import load_prompt, stream_analysis, DeepSeekError

def test_load_prompt_vocab(env):
    p = load_prompt("vocab")
    assert "词汇" in p or "学习者" in p

def test_load_prompt_invalid_category(env):
    with pytest.raises(ValueError):
        load_prompt("bogus")

async def test_stream_analysis_yields_tokens(env, httpx_mock):
    httpx_mock.add_response(
        url="https://api.deepseek.com/chat/completions",
        method="POST",
        text=(
            'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
            'data: [DONE]\n\n'
        ),
        headers={"Content-Type": "text/event-stream"},
    )
    tokens = []
    async for tok in stream_analysis("vocab", "advice", "He gave me some advice."):
        tokens.append(tok)
    assert "".join(tokens) == "hello world"

async def test_stream_analysis_http_error(env, httpx_mock):
    httpx_mock.add_response(
        url="https://api.deepseek.com/chat/completions",
        method="POST",
        status_code=500,
        text="server error",
    )
    with pytest.raises(DeepSeekError):
        async for _ in stream_analysis("vocab", "x", "y"):
            pass
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_deepseek.py -v
```
Expected: FAIL.

- [ ] **Step 4: Implement deepseek.py**

```python
# server/app/deepseek.py
import json
from pathlib import Path
from typing import AsyncIterator
import httpx
from app.config import load_config

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
VALID_CATEGORIES = {"vocab", "grammar", "structure"}
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

class DeepSeekError(RuntimeError):
    pass

def load_prompt(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    return (PROMPTS_DIR / f"{category}.txt").read_text(encoding="utf-8")

async def stream_analysis(
    category: str,
    selected_text: str,
    para_context: str,
) -> AsyncIterator[str]:
    """Yields response content tokens from DeepSeek."""
    system_prompt = load_prompt(category)
    user_msg = (
        f"选中文本：{selected_text}\n\n"
        f"完整段落上下文：\n{para_context}"
    )
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": True,
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {load_config().deepseek_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", DEEPSEEK_URL, json=body, headers=headers) as r:
            if r.status_code >= 400:
                body_text = await r.aread()
                raise DeepSeekError(f"DeepSeek {r.status_code}: {body_text[:200]!r}")
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return
                try:
                    obj = json.loads(payload)
                    delta = obj["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_deepseek.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add server/app/deepseek.py server/prompts/ server/tests/test_deepseek.py
git commit -m "feat(deepseek): streaming client with per-category prompts"
```

---

## Task 5: FastAPI app + admin routes

App factory pattern so tests can construct fresh app. Endpoints: `POST /admin/login`, `POST /admin/logout`, `GET /admin` (status JSON).

**Files:**
- Create: `server/app/main.py`
- Create: `server/app/routes/admin.py`
- Modify: `server/tests/test_routes.py` (new file)

- [ ] **Step 1: Write failing tests**

```python
# server/tests/test_routes.py
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth import SESSION_COOKIE

@pytest.fixture
def client(env):
    return TestClient(create_app())

def test_login_wrong_password(client):
    r = client.post("/admin/login", json={"password": "wrong"})
    assert r.status_code == 401

def test_login_correct_sets_cookie(client):
    r = client.post("/admin/login", json={"password": "test"})
    assert r.status_code == 200
    assert SESSION_COOKIE in r.cookies

def test_admin_status_requires_session(client):
    assert client.get("/admin").status_code == 401

def test_admin_status_with_session(client):
    client.post("/admin/login", json={"password": "test"})
    r = client.get("/admin")
    assert r.status_code == 200
    assert r.json() == {"role": "admin"}

def test_logout_clears_cookie(client):
    client.post("/admin/login", json={"password": "test"})
    r = client.post("/admin/logout")
    assert r.status_code == 200
    # subsequent admin call should fail
    assert client.get("/admin").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_routes.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement main.py**

```python
# server/app/main.py
from fastapi import FastAPI
from app.routes import admin

def create_app() -> FastAPI:
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    return app

app = create_app()  # for `uvicorn app.main:app`
```

- [ ] **Step 4: Implement admin.py**

```python
# server/app/routes/admin.py
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from app.auth import (
    verify_password, issue_session, require_admin,
    SESSION_COOKIE, SESSION_MAX_AGE,
)

router = APIRouter()

class LoginBody(BaseModel):
    password: str

@router.post("/admin/login")
def login(body: LoginBody, response: Response):
    if not verify_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="bad password")
    token = issue_session()
    response.set_cookie(
        key=SESSION_COOKIE, value=token,
        max_age=SESSION_MAX_AGE, httponly=True,
        samesite="lax", secure=False,  # nginx terminates TLS later; flip to True then
        path="/",
    )
    return {"ok": True}

@router.post("/admin/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}

@router.get("/admin")
def status(_: None = Depends(require_admin)):
    return {"role": "admin"}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_routes.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add server/app/main.py server/app/routes/
git add server/tests/test_routes.py
git commit -m "feat(api): admin login/logout/status with session cookies"
```

---

## Task 6: Notes routes (`/api/notes/<slug>`)

`GET` returns the list (auth required), `POST` appends a single note.

**Files:**
- Create: `server/app/routes/notes.py`
- Modify: `server/app/main.py` (register router)
- Modify: `server/tests/test_routes.py` (append tests)

- [ ] **Step 1: Append failing tests to test_routes.py**

```python
# additional tests in server/tests/test_routes.py
def _login(client):
    client.post("/admin/login", json={"password": "test"})

def test_get_notes_requires_auth(client):
    assert client.get("/api/notes/gatsby").status_code == 401

def test_get_notes_empty(client):
    _login(client)
    r = client.get("/api/notes/gatsby")
    assert r.status_code == 200
    assert r.json() == []

def test_post_and_get_roundtrip(client):
    _login(client)
    note = {
        "paraId": "para3",
        "category": "vocab",
        "selectedText": "advantages",
        "responseMarkdown": "**advantages** — 优势",
    }
    r = client.post("/api/notes/gatsby", json=note)
    assert r.status_code == 201
    r2 = client.get("/api/notes/gatsby")
    assert r2.status_code == 200
    body = r2.json()
    assert len(body) == 1
    assert body[0]["selectedText"] == "advantages"
    assert body[0]["createdAt"]

def test_post_rejects_bad_category(client):
    _login(client)
    bad = {"paraId": "p", "category": "bogus",
           "selectedText": "x", "responseMarkdown": "y"}
    r = client.post("/api/notes/gatsby", json=bad)
    assert r.status_code == 400

def test_post_rejects_bad_slug(client):
    _login(client)
    note = {"paraId": "p", "category": "vocab",
            "selectedText": "x", "responseMarkdown": "y"}
    r = client.post("/api/notes/..%2Fetc%2Fpasswd", json=note)
    assert r.status_code in (400, 404)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_routes.py -v -k notes
```
Expected: FAIL (404 — router not registered).

- [ ] **Step 3: Implement notes.py**

```python
# server/app/routes/notes.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.auth import require_admin
from app.notes import read_notes, append_note, Note, NoteValidationError

router = APIRouter()

class NoteIn(BaseModel):
    paraId: str = Field(min_length=1, max_length=64)
    category: str
    selectedText: str = Field(min_length=1, max_length=2000)
    responseMarkdown: str = Field(min_length=1, max_length=8000)

@router.get("/api/notes/{slug}")
def get_notes(slug: str, _: None = Depends(require_admin)):
    try:
        return [n.__dict__ for n in read_notes(slug)]
    except NoteValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/notes/{slug}", status_code=status.HTTP_201_CREATED)
def post_note(slug: str, body: NoteIn, _: None = Depends(require_admin)):
    note = Note(**body.model_dump())
    try:
        append_note(slug, note)
    except NoteValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "createdAt": note.createdAt}
```

- [ ] **Step 4: Register router in main.py**

Edit `server/app/main.py`:

```python
# server/app/main.py
from fastapi import FastAPI
from app.routes import admin, notes

def create_app() -> FastAPI:
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    return app

app = create_app()
```

Also: the public `GET /api/notes/<slug>` needs to work for non-admins (the script fetches on load even without login — it just gets an empty list or all notes regardless). Re-read the spec: "if an admin session cookie is present, fetch `GET /api/notes/<book-slug>` and inject saved notes". Actually the saved notes are public — anyone reading the page should see them. Change `get_notes` to NOT require auth:

```python
@router.get("/api/notes/{slug}")
def get_notes(slug: str):
    try:
        return [n.__dict__ for n in read_notes(slug)]
    except NoteValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

Update `test_get_notes_requires_auth` to assert 200 + empty list instead:

```python
def test_get_notes_is_public(client):
    r = client.get("/api/notes/gatsby")
    assert r.status_code == 200
    assert r.json() == []
```

(Replace the previous `test_get_notes_requires_auth` with this.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_routes.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/notes.py server/app/main.py server/tests/test_routes.py
git commit -m "feat(api): public GET notes, admin-only POST notes"
```

---

## Task 7: Query SSE route

`POST /api/query` streams DeepSeek output as server-sent events.

**Files:**
- Create: `server/app/routes/query.py`
- Modify: `server/app/main.py` (register)
- Modify: `server/tests/test_routes.py` (add)

- [ ] **Step 1: Add failing test**

```python
# server/tests/test_routes.py — append
def test_query_requires_auth(client):
    r = client.post("/api/query", json={
        "category": "vocab", "selectedText": "x", "paraContext": "y"
    })
    assert r.status_code == 401

def test_query_streams(client, httpx_mock):
    _login(client)
    httpx_mock.add_response(
        url="https://api.deepseek.com/chat/completions",
        method="POST",
        text=(
            'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            'data: [DONE]\n\n'
        ),
        headers={"Content-Type": "text/event-stream"},
    )
    with client.stream("POST", "/api/query", json={
        "category": "vocab",
        "selectedText": "advice",
        "paraContext": "He gave me some advice.",
    }) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode()
    assert "data: hi" in body
    assert "data: [DONE]" in body

def test_query_bad_category(client):
    _login(client)
    r = client.post("/api/query", json={
        "category": "bogus", "selectedText": "x", "paraContext": "y"
    })
    assert r.status_code == 422  # pydantic validation
```

- [ ] **Step 2: Run to verify fail**

```bash
.venv/bin/pytest tests/test_routes.py -v -k query
```
Expected: FAIL.

- [ ] **Step 3: Implement query.py**

```python
# server/app/routes/query.py
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.auth import require_admin
from app.deepseek import stream_analysis, DeepSeekError

router = APIRouter()

class QueryBody(BaseModel):
    category: Literal["vocab", "grammar", "structure"]
    selectedText: str = Field(min_length=1, max_length=2000)
    paraContext: str = Field(min_length=1, max_length=10000)

async def _sse(body: QueryBody):
    try:
        async for token in stream_analysis(body.category, body.selectedText, body.paraContext):
            # SSE: escape newlines per spec
            safe = token.replace("\r", "").replace("\n", "\\n")
            yield f"data: {safe}\n\n"
        yield "data: [DONE]\n\n"
    except DeepSeekError as e:
        yield f"event: error\ndata: {str(e)[:200]}\n\n"

@router.post("/api/query")
async def query(body: QueryBody, _: None = Depends(require_admin)):
    return StreamingResponse(_sse(body), media_type="text/event-stream")
```

- [ ] **Step 4: Register in main.py**

```python
# server/app/main.py
from fastapi import FastAPI
from app.routes import admin, notes, query

def create_app() -> FastAPI:
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    app.include_router(query.router)
    return app

app = create_app()
```

- [ ] **Step 5: Run tests to verify pass**

```bash
.venv/bin/pytest tests/test_routes.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/query.py server/app/main.py server/tests/test_routes.py
git commit -m "feat(api): streaming /api/query endpoint backed by DeepSeek"
```

---

## Task 8: Frontend — annotate.css

Standalone stylesheet for selection bar, popover, AI badge, fade-in.

**Files:**
- Create: `static/annotate.css`

- [ ] **Step 1: Write annotate.css**

```css
/* static/annotate.css */
.bi-sel-bar {
  position: absolute;
  display: flex;
  background: #1a1a1a;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.25);
  overflow: hidden;
  z-index: 9999;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
}
.bi-sel-bar button {
  background: none;
  border: 0;
  color: #fff;
  padding: 10px 16px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  border-right: 1px solid #333;
}
.bi-sel-bar button:last-child { border-right: 0; }
.bi-sel-bar button:hover { background: #2d2d2d; }
.bi-sel-bar .dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.bi-sel-bar .dot.v { background: #3a7bb5; }
.bi-sel-bar .dot.g { background: #b8924a; }
.bi-sel-bar .dot.s { background: #7a8a4e; }

.bi-pop {
  position: absolute;
  width: 380px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.2);
  z-index: 9999;
  overflow: hidden;
  border: 1px solid #d8cfb6;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
}
.bi-pop-hdr {
  padding: 10px 14px;
  background: #f7f3e9;
  border-bottom: 1px solid #e0d8c4;
  font-size: 12px;
  color: #7a7466;
  display: flex;
  justify-content: space-between;
}
.bi-pop-hdr .cat { font-weight: 600; }
.bi-pop-sel {
  padding: 8px 14px;
  background: #fdfaf2;
  font-size: 13px;
  color: #3a3830;
  border-bottom: 1px solid #f0e9d8;
  font-style: italic;
}
.bi-pop-body {
  padding: 14px;
  font-size: 13.5px;
  line-height: 1.65;
  color: #3a3830;
  max-height: 280px;
  overflow-y: auto;
  white-space: pre-wrap;
}
.bi-pop-foot {
  padding: 10px 14px;
  border-top: 1px solid #e0d8c4;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  background: #faf7ed;
}
.bi-pop-foot button {
  font-family: inherit;
  font-size: 12.5px;
  padding: 7px 14px;
  border-radius: 5px;
  border: 1px solid #c8bea0;
  background: #fff;
  cursor: pointer;
  color: #3a3830;
}
.bi-pop-foot button.primary {
  background: #3a7bb5;
  color: #fff;
  border-color: #3a7bb5;
  font-weight: 600;
}
.bi-pop-foot button[disabled] { opacity: 0.5; cursor: not-allowed; }
.bi-cursor {
  display: inline-block;
  width: 6px; height: 14px;
  background: currentColor;
  vertical-align: text-bottom;
  margin-left: 2px;
  animation: bi-blink 1s infinite;
}
@keyframes bi-blink { 50% { opacity: 0; } }

.bi-note-ai {
  border-top: 1px dashed #d8cfb6;
  padding-top: 10px;
  margin-top: 10px;
  animation: bi-fadein 0.4s;
}
.bi-ai-badge {
  display: inline-block;
  background: #111;
  color: #fff;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  margin-right: 6px;
  letter-spacing: 0.06em;
  vertical-align: middle;
}
@keyframes bi-fadein {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; }
}

.bi-pop-err { color: #b03030; padding: 14px; font-size: 13px; }
```

- [ ] **Step 2: Commit**

```bash
git add static/annotate.css
git commit -m "feat(frontend): annotation UI styles"
```

---

## Task 9: Frontend — annotate.js (selection bar + popover + save)

Single file, no build. Two main flows: (a) hydrate saved notes on load, (b) handle selection → query → save.

**Files:**
- Create: `static/annotate.js`

- [ ] **Step 1: Write annotate.js**

```javascript
// static/annotate.js
(() => {
  const BOOK_SLUG = (location.pathname.replace(/^\/+|\/+$/g, '').split('/')[0] || 'index')
                      .replace(/\.html$/, '');
  const CATEGORIES = [
    { key: 'vocab',     label: '词汇',       dot: 'v', color: '#3a7bb5' },
    { key: 'grammar',   label: '语法',       dot: 'g', color: '#b8924a' },
    { key: 'structure', label: '句子结构',   dot: 's', color: '#7a8a4e' },
  ];

  // ─── Hydration: load saved notes on page load ───────────────────
  async function hydrate() {
    try {
      const r = await fetch(`/api/notes/${BOOK_SLUG}`);
      if (!r.ok) return;
      const notes = await r.json();
      notes.forEach(renderSavedNote);
    } catch (_) { /* ignore */ }
  }

  function renderSavedNote(note) {
    const para = document.getElementById(note.paraId);
    if (!para) {
      console.warn('bi: paraId not found', note.paraId);
      return;
    }
    const hdr = para.querySelector(`.card-hdr.${note.category}`);
    if (!hdr) {
      console.warn('bi: subsection not found', note.paraId, note.category);
      return;
    }
    const body = hdr.nextElementSibling;
    if (!body) return;
    const div = document.createElement('div');
    div.className = 'bi-note-ai';
    div.innerHTML = `<span class="bi-ai-badge">AI</span>
                     <span class="bi-ai-sel">${escapeHtml(note.selectedText)}</span> —
                     <span class="bi-ai-body">${escapeHtml(note.responseMarkdown)}</span>`;
    body.appendChild(div);
  }

  // ─── Admin gate ─────────────────────────────────────────────────
  let isAdmin = false;
  async function checkAdmin() {
    try {
      const r = await fetch('/admin', { credentials: 'same-origin' });
      isAdmin = r.ok;
    } catch (_) { isAdmin = false; }
  }

  // ─── Selection bar ──────────────────────────────────────────────
  let currentBar = null;
  let currentPop = null;

  function teardown() {
    if (currentBar) { currentBar.remove(); currentBar = null; }
    if (currentPop) { currentPop.remove(); currentPop = null; }
  }

  document.addEventListener('mouseup', (e) => {
    if (!isAdmin) return;
    if (currentPop && currentPop.contains(e.target)) return;
    setTimeout(() => handleSelection(e), 0);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') teardown();
  });

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
    if (findParaSection(range.endContainer) !== para) return;  // single para only
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
      btn.onclick = (ev) => {
        ev.stopPropagation();
        bar.remove(); currentBar = null;
        openPopover(rect, para, text, c);
      };
      bar.appendChild(btn);
    });
    document.body.appendChild(bar);
    currentBar = bar;
  }

  // ─── Popover + streaming ────────────────────────────────────────
  function openPopover(rect, para, text, cat) {
    const pop = document.createElement('div');
    pop.className = 'bi-pop';
    pop.style.top  = (window.scrollY + rect.bottom + 8) + 'px';
    pop.style.left = (window.scrollX + rect.left) + 'px';
    pop.innerHTML = `
      <div class="bi-pop-hdr">
        <span><span class="cat" style="color:${cat.color}">${cat.label}</span> · DeepSeek</span>
        <span>${para.id}</span>
      </div>
      <div class="bi-pop-sel">"${escapeHtml(text)}"</div>
      <div class="bi-pop-body"></div>
      <div class="bi-pop-foot">
        <button class="bi-close">关闭</button>
        <button class="bi-save primary" disabled>保存到卡片</button>
      </div>
    `;
    document.body.appendChild(pop);
    currentPop = pop;
    const bodyEl  = pop.querySelector('.bi-pop-body');
    const saveBtn = pop.querySelector('.bi-save');
    const closeBtn = pop.querySelector('.bi-close');

    bodyEl.innerHTML = '<span class="bi-stream"></span><span class="bi-cursor"></span>';
    const streamEl = bodyEl.querySelector('.bi-stream');
    const cursorEl = bodyEl.querySelector('.bi-cursor');

    const paraText = (para.querySelector('.original') || para).innerText.trim();

    streamQuery(cat.key, text, paraText,
      (tok) => { streamEl.textContent += tok; },
      () => { cursorEl.remove(); saveBtn.disabled = false; },
      (err) => { bodyEl.innerHTML = `<div class="bi-pop-err">出错：${escapeHtml(err)}</div>`; }
    );

    closeBtn.onclick = teardown;
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      const note = {
        paraId: para.id,
        category: cat.key,
        selectedText: text,
        responseMarkdown: streamEl.textContent,
      };
      try {
        const r = await fetch(`/api/notes/${BOOK_SLUG}`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(note),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        renderSavedNote(note);
        teardown();
      } catch (e) {
        alert('保存失败: ' + e.message);
        saveBtn.disabled = false;
      }
    };
  }

  async function streamQuery(category, selectedText, paraContext, onToken, onDone, onError) {
    try {
      const r = await fetch('/api/query', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
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
            } else if (line.startsWith('event: error')) {
              // next line will be data:
            }
          }
        }
      }
      onDone();
    } catch (e) {
      onError(e.message);
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  // ─── Boot ───────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', async () => {
    await Promise.all([hydrate(), checkAdmin()]);
  });
})();
```

- [ ] **Step 2: Manually smoke-test locally**

Open `/Users/ben/Downloads/belowiceberg/gatsby-teaching-edition.html` in browser. The script will fail to fetch (no server yet), but should NOT throw uncaught errors. Open DevTools console; expect at most warnings from the failed fetch.

```bash
open /Users/ben/Downloads/belowiceberg/gatsby-teaching-edition.html
```
*(Note: script is not yet injected into the HTML — that happens in Task 11. This step just sanity-checks the JS parses.)*

To actually parse-check it, run:

```bash
node --check /Users/ben/Downloads/belowiceberg/static/annotate.js
```
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add static/annotate.js
git commit -m "feat(frontend): annotation script — hydrate, select, stream, save"
```

---

## Task 10: Wire the script into existing HTML pages

Add the CSS link and script tag at the bottom of `</body>` in both HTML files.

**Files:**
- Modify: `/Users/ben/Downloads/belowiceberg/gatsby-teaching-edition.html`
- Modify: `/Users/ben/Downloads/belowiceberg/belowiceberg-website-v2.html`

- [ ] **Step 1: Find each `</body>` and insert before it**

For each file, insert immediately before `</body>`:

```html
<link rel="stylesheet" href="/static/annotate.css">
<script src="/static/annotate.js" defer></script>
```

Use this command to verify the insertion afterward:

```bash
grep -n "annotate.js" /Users/ben/Downloads/belowiceberg/*.html
```
Expected: two matches (one per file).

- [ ] **Step 2: Commit**

```bash
git add belowiceberg-website-v2.html gatsby-teaching-edition.html
git commit -m "feat: include annotation script on teaching-edition pages"
```

---

## Task 11: Deployment artifacts (systemd + nginx)

Files committed to the repo; install script copies them into place on the server.

**Files:**
- Create: `deploy/belowiceberg-api.service`
- Create: `deploy/nginx-belowiceberg.conf`
- Create: `deploy/install.sh`

- [ ] **Step 1: Write systemd unit**

`deploy/belowiceberg-api.service`:

```ini
[Unit]
Description=belowiceberg FastAPI app
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/belowiceberg/server
EnvironmentFile=/etc/belowiceberg/admin.env
Environment=BELOWICEBERG_DATA_DIR=/var/www/belowiceberg-data
ExecStart=/opt/belowiceberg/server/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Write nginx config**

`deploy/nginx-belowiceberg.conf`:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    root /var/www/belowiceberg;
    index index.html;

    # Static files served directly
    location /static/ {
        alias /opt/belowiceberg/static/;
        access_log off;
        expires 1h;
    }

    # API: reverse proxy to uvicorn (preserve SSE)
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;        # critical for SSE
        proxy_cache off;
        proxy_read_timeout 120s;
    }

    location /admin {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    location = /gatsby { try_files /gatsby.html =404; }

    location / { try_files $uri $uri/ =404; }
}
```

- [ ] **Step 3: Write install.sh (run on the Vultr server)**

`deploy/install.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Run as root on the Vultr server after rsync'ing the repo to /opt/belowiceberg
REPO=/opt/belowiceberg

apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv

# Create data dirs
mkdir -p /var/www/belowiceberg-data/notes
chown -R www-data:www-data /var/www/belowiceberg-data
mkdir -p /etc/belowiceberg
chmod 750 /etc/belowiceberg

# Venv
if [ ! -d "$REPO/server/.venv" ]; then
  python3.11 -m venv "$REPO/server/.venv"
fi
"$REPO/server/.venv/bin/pip" install -q -e "$REPO/server"

# systemd unit
cp "$REPO/deploy/belowiceberg-api.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable belowiceberg-api.service
systemctl restart belowiceberg-api.service

# nginx
cp "$REPO/deploy/nginx-belowiceberg.conf" /etc/nginx/sites-available/belowiceberg
ln -sf /etc/nginx/sites-available/belowiceberg /etc/nginx/sites-enabled/belowiceberg
nginx -t
systemctl reload nginx

echo
echo "── Almost done. Now create /etc/belowiceberg/admin.env with:"
echo "ADMIN_PASSWORD_HASH=<bcrypt hash>"
echo "SESSION_SECRET=<random 32+ chars>"
echo "DEEPSEEK_API_KEY=<your key>"
echo "── Then: systemctl restart belowiceberg-api.service"
```

- [ ] **Step 4: chmod and commit**

```bash
chmod +x /Users/ben/Downloads/belowiceberg/deploy/install.sh
git add deploy/
git commit -m "feat(deploy): systemd unit, nginx config, install script"
```

---

## Task 12: Generate admin.env values

One-off helper to mint a bcrypt password hash and a session secret.

**Files:**
- Create: `deploy/gen-env.py`

- [ ] **Step 1: Write helper**

`deploy/gen-env.py`:

```python
#!/usr/bin/env python3
"""Generate admin.env contents. Run locally; paste output into /etc/belowiceberg/admin.env on server."""
import bcrypt
import secrets
import sys
import getpass

if __name__ == "__main__":
    pw = getpass.getpass("Admin password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw != pw2:
        sys.exit("Mismatch.")
    h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()
    s = secrets.token_urlsafe(48)
    print()
    print(f"ADMIN_PASSWORD_HASH={h}")
    print(f"SESSION_SECRET={s}")
    print("DEEPSEEK_API_KEY=<paste your DeepSeek key here>")
```

- [ ] **Step 2: Generate values for the Vultr server**

```bash
cd /Users/ben/Downloads/belowiceberg
server/.venv/bin/python deploy/gen-env.py
```
Pick a strong password. Copy the output. You will paste it into `/etc/belowiceberg/admin.env` on the server in Task 13.

You also need a DeepSeek API key from https://platform.deepseek.com — replace the placeholder line.

- [ ] **Step 3: Commit (the helper, not the secrets)**

```bash
git add deploy/gen-env.py
git commit -m "chore(deploy): helper to mint admin password hash and session secret"
```

---

## Task 13: Deploy to Vultr

Push code to the server and run the install script. Server IP `66.135.16.106`, root SSH (use the `/tmp/ssh_run.exp` and `/tmp/scp_run.exp` helpers from earlier in this session, or set up SSH keys first).

**Files:** none (operational task)

- [ ] **Step 1: Rsync repo to server**

From local machine:

```bash
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' \
  -e "ssh -o StrictHostKeyChecking=no" \
  /Users/ben/Downloads/belowiceberg/ \
  root@66.135.16.106:/opt/belowiceberg/
```

If the previous session's password helper is still around:

```bash
/tmp/scp_run.exp '<root password>' /Users/ben/Downloads/belowiceberg/ /opt/belowiceberg/
```
(rsync is preferable. Set up SSH keys first if not already done.)

- [ ] **Step 2: Run install on server**

```bash
ssh root@66.135.16.106 'bash /opt/belowiceberg/deploy/install.sh'
```
Expected: nginx reloads, systemd reports service enabled. The service will START FAILING on the loop until admin.env exists — that's fine.

- [ ] **Step 3: Create admin.env on server**

Paste the output from Task 12 step 2 into the file:

```bash
ssh root@66.135.16.106 'cat > /etc/belowiceberg/admin.env <<EOF
ADMIN_PASSWORD_HASH=<paste>
SESSION_SECRET=<paste>
DEEPSEEK_API_KEY=<paste>
EOF
chmod 600 /etc/belowiceberg/admin.env
systemctl restart belowiceberg-api.service'
```

- [ ] **Step 4: Verify service is up**

```bash
ssh root@66.135.16.106 'systemctl status belowiceberg-api.service --no-pager | head -20'
```
Expected: `Active: active (running)`.

```bash
ssh root@66.135.16.106 'curl -s http://127.0.0.1:8001/admin'
```
Expected: `{"detail":"admin login required"}` (401 — auth working).

- [ ] **Step 5: Verify nginx routing**

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://66.135.16.106/api/notes/gatsby
curl -s -o /dev/null -w '%{http_code}\n' http://66.135.16.106/static/annotate.js
```
Expected: `200` and `200`.

- [ ] **Step 6: Commit deploy log**

```bash
cd /Users/ben/Downloads/belowiceberg
git commit --allow-empty -m "deploy: initial production rollout to 66.135.16.106"
```

---

## Task 14: End-to-end smoke test

Use a real browser. The verification path is manual because the feature is inherently interactive.

**Files:** none

- [ ] **Step 1: Log in**

In a browser, open DevTools → Network, then:

```bash
curl -i -X POST http://66.135.16.106/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"<your password>"}'
```
Expected: `200 OK` and a `Set-Cookie: belowiceberg_session=...` header.

(Or just open `http://66.135.16.106/gatsby` in your browser and POST via the browser console — you need the cookie set in the browser.)

To set the cookie from the browser console:
```javascript
await fetch('/admin/login', {
  method: 'POST', headers: {'Content-Type':'application/json'},
  body: JSON.stringify({password:'<your password>'})
});
```

- [ ] **Step 2: Reload `/gatsby` and select a word in the first paragraph**

Expected:
- Dark floating bar with 词汇/语法/句子结构 appears above the selection.
- Console has no errors.

- [ ] **Step 3: Click 词汇**

Expected:
- Bar disappears; popover appears below the selection.
- Text streams in. Blinking cursor visible.
- "保存到卡片" button enables once stream finishes.

- [ ] **Step 4: Click 保存到卡片**

Expected:
- Popover closes.
- New note with black "AI" badge appears at the bottom of that paragraph's vocab subsection.

- [ ] **Step 5: Hard-reload the page**

Expected:
- The saved note is still there (loaded from `/api/notes/gatsby`).

- [ ] **Step 6: Verify the sidecar on the server**

```bash
ssh root@66.135.16.106 'cat /var/www/belowiceberg-data/notes/gatsby.json'
```
Expected: a JSON array with your saved note.

- [ ] **Step 7: Log out, reload, confirm bar does NOT appear**

```javascript
// in browser console
await fetch('/admin/logout', {method:'POST'});
```
Reload `/gatsby`. Selecting text should NOT show the bar. Saved notes should still render (public read).

- [ ] **Step 8: Commit a notes log entry**

```bash
git commit --allow-empty -m "verify: e2e smoke test passed on /gatsby"
```

---

## Self-Review Notes (for the implementer)

If anything in this plan turns out wrong during implementation, the spec is the source of truth: `docs/superpowers/specs/2026-05-23-annotation-system-design.md`. The most likely discrepancies you'll hit:

- **DeepSeek SSE format**: their actual stream format may differ slightly from the OpenAI-style format assumed here. Test against a real key early in Task 4.
- **`para.querySelector('.original')`** assumes paragraphs in the gatsby HTML wrap original text in `.original`. Verify by inspecting the actual HTML; if the class differs, update the JS to fall back to the para itself (already does).
- **`samesite=lax` + `secure=False`** works on HTTP. When you add HTTPS later, flip `secure=True`.
