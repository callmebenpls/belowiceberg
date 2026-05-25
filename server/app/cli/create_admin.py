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
