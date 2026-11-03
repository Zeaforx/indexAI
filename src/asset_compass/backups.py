"""Recoverable SQLite snapshots with an atomic, never-overwrite destination.

The SQLite backup API takes a transactionally consistent snapshot even when the
source is in WAL mode. This module deliberately does not implement PostgreSQL
backups: use PostgreSQL's own pg_dump/restore tooling for those deployments.
"""

import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import quote
from contextlib import closing

from sqlalchemy.engine import make_url


REQUIRED_TABLES = frozenset({"alembic_version", "resources", "sources", "tags", "resource_tags"})


def _sqlite_path(database_url: str) -> Path:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite":
        raise ValueError("This command supports file-backed SQLite only; use pg_dump for PostgreSQL")
    if not parsed.database or parsed.database == ":memory:" or parsed.query.get("uri"):
        raise ValueError("A standard file-backed SQLite URL is required")
    return Path(parsed.database).expanduser().resolve()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ValueError(f"SQLite snapshot/database does not exist: {path}")
    return sqlite3.connect(f"file:{quote(str(path.resolve()))}?mode=ro", uri=True, timeout=15)


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify_snapshot(path: Path) -> dict:
    """Verify SQLite structural/foreign-key integrity and catalog shape.

    This proves the copy is internally consistent at verification time, not
    that an old/third-party dataset contains legally usable asset files.
    """
    path = Path(path)
    with closing(_connect_read_only(path)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError("SQLite integrity_check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("SQLite foreign key violations detected")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES.issubset(tables):
            raise ValueError("Not an initialized indexAI catalog database")
        version = db.execute("SELECT version_num FROM alembic_version").fetchone()
        if not version or not version[0]:
            raise ValueError("Missing catalog schema version")
        resources = db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        sources = db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    return {
        "path": str(path.resolve()), "schema_version": version[0],
        "resources": resources, "sources": sources,
        "bytes": path.stat().st_size, "sha256": _digest(path), "integrity": "ok",
    }


def _atomic_snapshot(source: Path, destination: Path) -> dict:
    destination = Path(destination)
    if destination.suffix.lower() not in {".sqlite3", ".db"}:
        raise ValueError("Snapshot destination must end in .sqlite3 or .db")
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Destination already exists; refusing to overwrite: {destination}")
    if not destination.parent.is_dir():
        raise ValueError(f"Destination directory does not exist: {destination.parent}")

    file_id, temporary = tempfile.mkstemp(prefix=".indexai-snapshot-", suffix=".tmp", dir=destination.parent)
    os.close(file_id)
    try:
        with closing(_connect_read_only(source)) as original:
            with closing(sqlite3.connect(temporary, timeout=15)) as target:
                original.backup(target, pages=128, sleep=0.05)
        verify_snapshot(Path(temporary))
        # Hard-link creation is atomic on this filesystem and fails if the
        # destination appeared in the meantime; no replacement is possible.
        os.link(temporary, destination)
        return verify_snapshot(destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def backup_catalog(database_url: str, destination: Path) -> dict:
    """Copy the active file-backed SQLite database to a *new* verified file."""
    source = _sqlite_path(database_url)
    verify_snapshot(source)
    return _atomic_snapshot(source, Path(destination))


def restore_catalog(snapshot: Path, destination: Path) -> dict:
    """Restore to a *new* database path; never replace the running catalog."""
    source = Path(snapshot)
    verify_snapshot(source)
    return _atomic_snapshot(source, Path(destination))
