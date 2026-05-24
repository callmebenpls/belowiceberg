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
