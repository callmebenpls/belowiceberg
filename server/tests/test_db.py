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
    assert cur.fetchone()[0] == 2

def test_get_conn_returns_same_connection_within_process(db):
    from app.db import get_conn
    assert get_conn() is get_conn()
