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
    conn = get_conn()
    existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        raise UserExistsError(f"email already registered: {email}")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
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
