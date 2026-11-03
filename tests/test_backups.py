"""Session 6 recovery: consistent, verified snapshots and no silent overwrite."""

import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from asset_compass.backups import backup_catalog, restore_catalog, verify_snapshot
from asset_compass.cli import app
from asset_compass.db import initialize, make_engine, open_session
from asset_compass.ingestion.batch import import_records, load_records
from asset_compass.models import Resource


def initialized_catalog(tmp_path):
    db_file = tmp_path / "catalog.sqlite3"
    db_url = f"sqlite:///{db_file}"
    engine = make_engine(db_url)
    initialize(engine)
    with open_session(engine) as session:
        rows = load_records(Path(__file__).resolve().parents[1] / "data/seed_kenney.json")
        assert import_records(session, rows)["created"] == 10
    engine.dispose()
    return db_url


def test_backup_verify_restore_and_query_again(tmp_path):
    database_url = initialized_catalog(tmp_path)
    source = tmp_path / "catalog.sqlite3"
    before = source.stat().st_size
    snapshot = tmp_path / "snapshot.sqlite3"
    destination = tmp_path / "restored.sqlite3"
    report = backup_catalog(database_url, snapshot)
    assert snapshot.is_file()
    assert report["integrity"] == "ok"
    assert report["resources"] == 10 and report["sources"] == 1
    assert report["schema_version"] == "0004"
    assert len(report["sha256"]) == 64
    assert verify_snapshot(snapshot) == report
    restored = restore_catalog(snapshot, destination)
    assert restored["resources"] == 10
    assert restored["sha256"] == report["sha256"]
    assert source.stat().st_size == before  # original catalog was never rewritten
    engine = make_engine(f"sqlite:///{destination}")
    with open_session(engine) as session:
        assert session.scalar(select(func.count(Resource.id))) == 10
    engine.dispose()


def test_backup_and_restore_never_overwrite_existing_files(tmp_path):
    url = initialized_catalog(tmp_path)
    occupied = tmp_path / "occupied.sqlite3"
    occupied.write_bytes(b"user data")
    with pytest.raises(ValueError, match="already exists"):
        backup_catalog(url, occupied)
    assert occupied.read_bytes() == b"user data"
    saved = tmp_path / "saved.sqlite3"
    backup_catalog(url, saved)
    with pytest.raises(ValueError, match="already exists"):
        restore_catalog(saved, occupied)
    assert occupied.read_bytes() == b"user data"
    with pytest.raises(ValueError, match="already exists"):
        restore_catalog(saved, tmp_path / "catalog.sqlite3")


def test_invalid_snapshot_or_configuration_fails_without_destination(tmp_path):
    invalid = tmp_path / "corrupt.sqlite3"
    invalid.write_bytes(b"not a SQLite database")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        restore_catalog(invalid, tmp_path / "should-not-appear.sqlite3")
    assert not (tmp_path / "should-not-appear.sqlite3").exists()
    with pytest.raises(ValueError, match="file-backed SQLite"):
        backup_catalog("postgresql+psycopg://user:pass@localhost/test", tmp_path / "pg.sqlite3")
    with pytest.raises(ValueError, match="file-backed SQLite"):
        backup_catalog("sqlite:///:memory:", tmp_path / "memory.sqlite3")
    with pytest.raises(ValueError, match="does not exist"):
        verify_snapshot(tmp_path / "absent.sqlite3")


def test_recovery_cli_reports_sha256_and_refuses_replacement(tmp_path, monkeypatch):
    url = initialized_catalog(tmp_path)
    monkeypatch.setenv("ASSET_COMPASS_DB_URL", url)
    runner = CliRunner()
    backup = tmp_path / "backup.sqlite3"
    saved = runner.invoke(app, ["backup", str(backup)])
    assert saved.exit_code == 0, saved.output
    assert json.loads(saved.output)["resources"] == 10
    verification = runner.invoke(app, ["verify-backup", str(backup)])
    assert verification.exit_code == 0, verification.output
    assert json.loads(verification.output)["sha256"] == json.loads(saved.output)["sha256"]
    restored = tmp_path / "recovered.sqlite3"
    reply = runner.invoke(app, ["restore", str(backup), "--to", str(restored)])
    assert reply.exit_code == 0, reply.output
    assert json.loads(reply.output)["resources"] == 10
    assert runner.invoke(app, ["restore", str(backup), "--to", str(restored)]).exit_code == 1
