from pathlib import Path
import os
import sqlite3
import sys

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.backup_db import backup_sqlite, postgres_args  # noqa: E402
from scripts.restore_db import restore_sqlite, postgres_connection  # noqa: E402


def make_database(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        db.execute("INSERT INTO marker(value) VALUES ('preserved')")


def test_sqlite_backup_and_restore_are_consistent_and_non_overwriting(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "private-backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    make_database(source)

    backup_sqlite(make_url(f"sqlite:///{source}"), backup)
    if os.name != "nt":
        assert backup.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT value FROM marker").fetchone() == ("preserved",)

    restore_sqlite(backup, restored)
    if os.name != "nt":
        assert restored.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT value FROM marker").fetchone() == ("preserved",)
    try:
        restore_sqlite(backup, restored)
    except SystemExit as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("SQLite restore unexpectedly overwrote an existing target")


def test_postgres_password_is_only_passed_through_environment():
    url = make_url("postgresql+psycopg://ssams_user:private%20secret@db.example.test:5432/ssams?sslmode=verify-full")
    dump_args, dump_env = postgres_args(url, "pg_dump")
    restore_args, restore_env = postgres_connection(url, "pg_restore")
    assert "private secret" not in " ".join(dump_args + restore_args)
    assert dump_env["PGPASSWORD"] == restore_env["PGPASSWORD"] == "private secret"
    assert dump_env["PGSSLMODE"] == restore_env["PGSSLMODE"] == "verify-full"
