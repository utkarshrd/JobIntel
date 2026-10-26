"""
Set (or reset) the password of an existing account. Operator tool, e.g. for accounts created before passwords existed.

  python scripts/set_password.py someone@example.com          # prompts for the new password (not echoed)

The password is stored only as a salted scrypt hash. Run it on the machine that has the database.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.database import SessionLocal  # noqa: E402
from backend.app.core.security import MIN_PASSWORD_LENGTH, hash_password  # noqa: E402
from backend.app.models import User  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/set_password.py <email>")
    email = sys.argv[1].strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email.ilike(email)).first()
        if not user:
            sys.exit(f"No account with email {email}")
        pw = getpass.getpass(f"New password for {user.email} (min {MIN_PASSWORD_LENGTH} chars): ")
        if len(pw) < MIN_PASSWORD_LENGTH or pw != getpass.getpass("Repeat password: "):
            sys.exit("Password too short or the two entries differ; nothing changed.")
        user.password_hash = hash_password(pw)
        db.commit()
        print(f"Password set for {user.email}. You can now sign in at /ui/.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
