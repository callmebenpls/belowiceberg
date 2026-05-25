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
