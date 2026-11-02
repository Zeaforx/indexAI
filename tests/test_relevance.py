"""Session 3: strict filters, source routing and cross-backend FTS shape."""

import json
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from asset_compass.catalog import (
    CatalogError, _fts_candidates, add_resource, add_source, find_sources,
    review_resource, search_resources,
)
from asset_compass.evaluation import run_evaluation
from asset_compass.ingestion.batch import import_records, load_records
from asset_compass.models import Resource
from asset_compass.relevance import infer_dimension, query_terms
from asset_compass.db import open_session

ROOT = Path(__file__).resolve().parents[1]


def test_query_normalization_ignores_prompt_instructions():
    assert query_terms("Please find free 3D low poly trees for my game") == {"low-poly", "tree"}
    assert query_terms("2D pixel art tilesets") == {"pixel-art", "tileset"}
    assert infer_dimension("Need 3D models") == "3d"
    assert infer_dimension("2D or 3D") is None


def test_search_strict_filters_and_evidence(engine):
    with open_session(engine) as session:
        source, _ = add_source(session, "https://example.org", "Custom Source")
        first, _ = add_resource(
            session, url="https://example.org/forest", source_id=source.id,
            title="Low Poly Forest", dimension="3d", kind="model",
            tags="low poly,forest,tree", formats="glb,blend", access="free",
            license_id="CC0-1.0", license_url="https://example.org/license",
            license_status="claimed",
        )
        other, _ = add_resource(
            session, url="https://example.org/forest-unknown", source_id=source.id,
            title="Forest Trees", dimension="3d", kind="model",
            tags="forest,tree", access="unknown",
        )
        review_resource(session, first.id, status="approved", method="ai-assisted")
        review_resource(session, other.id, status="approved", method="automated")
    with open_session(engine) as session:
        filters = dict(dimension="3d", style="low poly", subject="forest", format="GLB", access="free", license_id="cc0-1.0", license_status="claimed")
        hits = search_resources(session, "low-poly tree", **filters)
        assert len(hits) == 1 and hits[0]["title"] == "Low Poly Forest"
        assert "tag:low-poly" in hits[0]["match_reasons"]
        assert hits[0]["license"]["status"] == "claimed"
        assert search_resources(session, "forest", format="fbx") == []
        assert search_resources(session, "forest", format="glb", license_status="verified") == []
        assert search_resources(session, "forest", subject="water") == []
        with pytest.raises(CatalogError):
            search_resources(session, "forest", format="glb,fbx")
        assert search_resources(session, "forest", dimension="2d") == []


def test_distinctive_query_beats_generic_old(engine):
    with open_session(engine) as session:
        source, _ = add_source(session, "https://example.org", "Models")
        for i in range(15):
            resource, _ = add_resource(
                session, source_id=source.id, url=f"https://example.org/old-{i}",
                title=f"Old Item {i}", dimension="3d", kind="model", tags="old",
            )
            review_resource(session, resource.id, status="approved", method="automated")
        specific, _ = add_resource(
            session, source_id=source.id, url="https://example.org/binoculars",
            title="Binoculars", dimension="3d", kind="model", tags="optical",
        )
        review_resource(session, specific.id, status="approved", method="human")
    with open_session(engine) as session:
        assert search_resources(session, "old binoculars", limit=1)[0]["title"] == "Binoculars"


def test_source_routes_from_real_seeds_and_benchmark(engine):
    with open_session(engine) as session:
        kenney = import_records(session, load_records(ROOT / "data/seed_kenney.json"))
        poly = import_records(session, load_records(ROOT / "data/seed_polyhaven.json"))
        assert kenney["created"] == 10 and poly["created"] == 35
    with open_session(engine) as session:
        assert search_resources(session, "3d flying dragon animations") == []
        source = find_sources(session, "3d flying dragon animations")
        assert len(source) == 1 and source[0]["name"] == "Poly Haven"
        assert source[0]["indexed_matches"] == 0
        assert source[0]["browse_url"] == "https://polyhaven.com/models"
        assert "Poly Haven" in source[0]["attribution_notice"]
        assert find_sources(session, "2d zombie character sprites")[0]["browse_url"] == "https://kenney.nl/assets"
        assert find_sources(session, "3d castle door")[0]["indexed_matches"] >= 1
        cases = json.loads((ROOT / "data/evaluation_queries.json").read_text(encoding="utf-8"))["cases"]
        report = run_evaluation(session, cases)
        assert report["cases"] == 33
        assert report["passed"] == 33, [item for item in report["details"] if not item["passed"]]


def test_pending_source_not_discovered(engine):
    with open_session(engine) as session:
        source, _ = add_source(session, "https://example.org", "Unreviewed")
        add_resource(session, source_id=source.id, url="https://example.org/x", title="Dragon", dimension="3d", kind="model")
        assert find_sources(session, "3d dragon") == []


def test_postgres_fts_query_compiles_with_binds():
    statement = select(Resource).where(_fts_candidates({"forest", "low-poly"}))
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "to_tsvector('english'::regconfig" in sql
    assert "websearch_to_tsquery('english'::regconfig" in sql
    assert "@@" in sql
    assert "EXISTS" in sql


def test_postgres_gin_migration_shape(monkeypatch):
    revision = import_module("asset_compass.migrations.versions.0003_postgres_search")
    statements = []
    monkeypatch.setattr(revision.op, "get_bind", lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    monkeypatch.setattr(revision.op, "execute", statements.append)
    revision.upgrade()
    assert len(statements) == 1
    assert "USING GIN" in statements[0]
    assert "to_tsvector('english'::regconfig" in statements[0]
    revision.downgrade()
    assert "DROP INDEX" in statements[1]
