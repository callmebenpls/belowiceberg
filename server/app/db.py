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
