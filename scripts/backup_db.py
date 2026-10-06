#!/usr/bin/env python3
"""Create a private, consistent SQLite or PostgreSQL database backup."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[1]
if os.name != "nt":
    os.umask(0o077)
load_dotenv(ROOT / ".env")


def sqlite_path(url: URL) -> Path:
    if not url.database:
        raise SystemExit("DATABASE_URL does not name a SQLite database file")
    path = Path(url.database).expanduser()
    # SQLAlchemy resolves relative SQLite paths against the backend process CWD.
    if not path.is_absolute():
        path = ROOT / "backend" / path
    return path.resolve()


def postgres_args(url: URL, executable: str) -> tuple[list[str], dict[str, str]]:
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


def backup_sqlite(url: URL, output: Path) -> None:
    source_path = sqlite_path(url)
    if not source_path.is_file():
        raise SystemExit(f"SQLite database file not found: {source_path}")
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True, timeout=15)
    target = sqlite3.connect(output, timeout=15)
    try:
        if os.name != "nt":
            output.chmod(0o600)
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("The backup failed SQLite integrity_check")
    finally:
        target.close()
        source.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New backup file; existing files are never overwritten")
    args = parser.parse_args()
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        raise SystemExit("DATABASE_URL is missing. Configure it in the private repository .env file.")
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite an existing backup: {output}")
    url = make_url(raw_url)
    try:
        if url.get_backend_name() == "sqlite":
            backup_sqlite(url, output)
        elif url.get_backend_name() == "postgresql":
            command, env = postgres_args(url, "pg_dump")
            command.extend(("--format=custom", f"--file={output}", "--no-owner", "--no-privileges"))
            subprocess.run(command, env=env, check=True)
        else:
            raise SystemExit(f"Unsupported database dialect: {url.get_backend_name()}")
    except FileNotFoundError as exc:
        output.unlink(missing_ok=True)
        raise SystemExit(f"Required database utility was not found: {exc.filename}") from exc
    except subprocess.CalledProcessError as exc:
        output.unlink(missing_ok=True)
        raise SystemExit(f"pg_dump failed with exit code {exc.returncode}; the backup was removed.") from exc
    except Exception:
        output.unlink(missing_ok=True)
        raise
    if os.name != "nt":
        output.chmod(0o600)
    print(f"Database backup created: {output} ({output.stat().st_size:,} bytes). Store it encrypted and restrict access.")


if __name__ == "__main__":
    main()
