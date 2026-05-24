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
