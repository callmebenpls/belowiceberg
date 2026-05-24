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
