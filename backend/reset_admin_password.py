
from getpass import getpass

from sqlalchemy import text
from app.db.session import engine
from app.core.security import hash_password

email = input("Admin email: ").strip().lower()
password = getpass("Enter new password (minimum 12 characters): ")
confirm = getpass("Confirm new password: ")

if len(password) < 12:
    raise SystemExit("Password must be at least 12 characters.")
if password != confirm:
    raise SystemExit("Passwords do not match.")

with engine.begin() as connection:
    result = connection.execute(
        text("""
            UPDATE users
            SET password_hash = :password_hash,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE email = :email AND role = 'admin'
        """),
        {
            "password_hash": hash_password(password),
            "email": email,
        },
    )
    if result.rowcount != 1:
        raise SystemExit("Exactly one admin account was not found; no reset completed.")

print("Admin password updated successfully.")
