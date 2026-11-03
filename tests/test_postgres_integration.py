"""Live PostgreSQL migration and retrieval test, enabled by CI service only."""

import os
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from asset_compass.catalog import search_resources
from asset_compass.db import initialize, make_engine, open_session
from asset_compass.ingestion.batch import import_records, load_records


POSTGRES_URL = os.environ.get("ASSET_COMPASS_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="No dedicated PostgreSQL test server configured")
def test_actual_postgres_schema_fts_and_tag_lookup():
    engine = make_engine(POSTGRES_URL)
    assert engine.dialect.name == "postgresql"
    try:
        initialize(engine)
        assert {"last_checked_at", "last_http_status"}.issubset(
            {column["name"] for column in inspect(engine).get_columns("resources")}
        )
        data = Path(__file__).resolve().parents[1] / "data"
        with open_session(engine) as session:
            for name, count in (
                ("seed_kenney.json", 10),
                ("seed_polyhaven.json", 35),
                ("seed_ambientcg_materials.json", 30),
            ):
                report = import_records(session, load_records(data / name))
                assert report["created"] == count and report["errors"] == []
        with open_session(engine) as session:
            gin = session.execute(text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'resources' AND indexname = 'ix_resources_search_english_gin'"
            )).scalar_one()
            assert gin == "ix_resources_search_english_gin"
            by_title = search_resources(session, "3d vintage binoculars", dimension="3d", limit=5)
            assert by_title and by_title[0]["title"] == "Binoculars"
            # Generic PBR has no occurrences in titles: this checks the
            # relational tag-only candidate branch of the PostgreSQL search.
            by_tag = search_resources(session, "pbr", dimension="3d", limit=5)
            assert by_tag and all("pbr" in item["tags"] for item in by_tag)
    finally:
        engine.dispose()
