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
