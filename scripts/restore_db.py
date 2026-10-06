#!/usr/bin/env python3
"""Restore into a NEW empty database; this tool never drops existing objects."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import subprocess

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[1]
if os.name != "nt":
    os.umask(0o077)
load_dotenv(ROOT / ".env")


def sqlite_path(url: URL) -> Path:
    if not url.database:
        raise SystemExit("DATABASE_URL does not name a SQLite database file")
    path = Path(url.database).expanduser()
    if not path.is_absolute():
        path = ROOT / "backend" / path
    return path.resolve()


def postgres_connection(url: URL, executable: str) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    args: list[str] = [executable]
    for option, value in (("--host", url.host), ("--port", str(url.port) if url.port else None),
                          ("--username", url.username), ("--dbname", url.database)):
        if value:
            args.extend((option, value))
    query_env = {"sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT", "sslcert": "PGSSLCERT",
                 "sslkey": "PGSSLKEY", "application_name": "PGAPPNAME", "connect_timeout": "PGCONNECT_TIMEOUT"}
    for key, variable in query_env.items():
        if key in url.query:
            value = url.query[key]
            env[variable] = str(value[0] if isinstance(value, (tuple, list)) else value)
    args.append("--no-password")
    return args, env


def require_empty_postgres(url: URL) -> None:
    engine = create_engine(url)
    try:
        tables = inspect(engine).get_table_names()
        if tables:
            raise SystemExit("Target PostgreSQL database is not empty; refusing to overwrite existing tables.")
    finally:
        engine.dispose()


def restore_sqlite(source: Path, target: Path) -> None:
    if target.exists():
        raise SystemExit(f"SQLite restore target already exists; refusing to overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_db = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=15)
    target_db = sqlite3.connect(target, timeout=15)
    try:
        if os.name != "nt":
            target.chmod(0o600)
        source_db.backup(target_db)
        result = target_db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("Restored SQLite database failed integrity_check")
    except Exception:
        target_db.close()
        source_db.close()
        target.unlink(missing_ok=True)
        raise
    else:
        target_db.close()
        source_db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="SQLite file or pg_dump custom-format backup")
    parser.add_argument("--confirm-target", required=True, help="Must exactly match the database name in DATABASE_URL")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Backup file not found: {source}")
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        raise SystemExit("DATABASE_URL is missing. Set it to a new, empty restore target in the private .env file.")
    url = make_url(raw_url)
    target_name = Path(url.database or "").name if url.get_backend_name() == "sqlite" else (url.database or "")
    if not target_name or args.confirm_target != target_name:
        raise SystemExit("--confirm-target must exactly match the target database name from DATABASE_URL")
    try:
        if url.get_backend_name() == "sqlite":
            restore_sqlite(source, sqlite_path(url))
        elif url.get_backend_name() == "postgresql":
            require_empty_postgres(url)
            command, env = postgres_connection(url, "pg_restore")
            command.extend(("--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges", str(source)))
            subprocess.run(command, env=env, check=True)
        else:
            raise SystemExit(f"Unsupported database dialect: {url.get_backend_name()}")
    except FileNotFoundError as exc:
        raise SystemExit(f"Required database utility was not found: {exc.filename}") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"pg_restore failed with exit code {exc.returncode}; no existing tables were dropped.") from exc
    print(f"Restore completed into new database '{target_name}'. Verify the data and migrations before changing production traffic.")


if __name__ == "__main__":
    main()
