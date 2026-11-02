import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from asset_compass.catalog import (
    CatalogError, add_resource, add_source, annotate_resource, get_resource,
    review_resource, search_resources,
)
from asset_compass.db import open_session
from asset_compass.models import Resource, Source
from asset_compass.seed import seed_demo


def _make(engine):
    with open_session(engine) as session:
        source, _ = add_source(session, "https://example.org/library", "Test Library")
        resource, _ = add_resource(
            session, source_id=source.id, url="https://example.org/tree?utm_source=test&id=7",
            title="Low Poly Fantasy Trees", description="Forest environment asset pack",
            dimension="3d", kind="model", tags="low poly,tree,forest",
            formats="gltf,blend", access="free",
        )
        return source.id, resource.id


def test_persistence_deduplication_and_foreign_keys(engine):
    source_id, resource_id = _make(engine)
    with open_session(engine) as session:
        same_source, source_created = add_source(session, "https://EXAMPLE.org/library#top", "Duplicate")
        same_resource, resource_created = add_resource(
            session, source_id=source_id, url="https://example.org/tree?id=7",
            title="Duplicate URL", dimension="3d", kind="model",
        )
        assert not source_created and same_source.id == source_id
        assert not resource_created and same_resource.id == resource_id
    with open_session(engine) as session:
        assert session.scalar(select(Source).where(Source.id == source_id)).name == "Test Library"
        resource = get_resource(session, resource_id)
        assert resource.formats == ["blend", "gltf"]
        assert sorted(t.slug for t in resource.tags) == ["forest", "low-poly", "tree"]
        assert resource.review_status == "pending"
        assert resource.canonical_url == "https://example.org/tree?id=7"


def test_review_required_and_search_filters(engine):
    _, resource_id = _make(engine)
    with open_session(engine) as session:
        assert search_resources(session, "forest") == []
        with pytest.raises(CatalogError):
            review_resource(session, resource_id, status="approved", method="none")
        review_resource(session, resource_id, status="approved", method="ai-assisted", note="Evidence check pending")
    with open_session(engine) as session:
        hits = search_resources(session, "low poly forest", dimension="3d", kind="model", tag="low poly", access="free")
        assert len(hits) == 1
        assert hits[0]["title"] == "Low Poly Fantasy Trees"
        assert hits[0]["review_method"] == "ai-assisted"
        assert search_resources(session, "forest", dimension="2d") == []
        assert search_resources(session, "forest", tag="pixel-art") == []


def test_annotation_replaces_tags_and_checks_license_evidence(engine):
    _, resource_id = _make(engine)
    with open_session(engine) as session:
        with pytest.raises(CatalogError):
            annotate_resource(session, resource_id, license_id="CC0-1.0", license_status="verified")
        resource = annotate_resource(
            session, resource_id, tags="environment,lowpoly", formats="glb",
            description="Updated description", license_id="CC0-1.0",
            license_url="https://example.org/license", license_status="verified",
        )
        assert sorted(tag.slug for tag in resource.tags) == ["environment", "low-poly"]
        assert resource.formats == ["glb"]
        assert resource.license_status == "verified"
    with open_session(engine) as session:
        resource = get_resource(session, resource_id)
        assert resource.description == "Updated description"
        assert resource.license_url == "https://example.org/license"


def test_invalid_metadata_fails_without_partial_insert(engine):
    with open_session(engine) as session:
        source, _ = add_source(session, "https://example.org", "Example")
        with pytest.raises(ValueError):
            add_resource(
                session, url="https://example.org/a", source_id=source.id,
                title="Invalid", dimension="4d", kind="model",
            )
        with pytest.raises(ValueError):
            add_resource(
                session, url="https://example.org/b", source_id=source.id,
                title="Invalid license", dimension="3d", kind="model",
                license_id="CC0-1.0", license_status="verified",
            )
    with open_session(engine) as session:
        assert session.scalar(select(Resource)) is None


def test_seed_is_idempotent_and_synthetic(engine):
    with open_session(engine) as session:
        assert seed_demo(session) == 10
    with open_session(engine) as session:
        assert seed_demo(session) == 0
        results = search_resources(session, "low poly forest", dimension="3d")
        assert [row["title"] for row in results] == ["Low Poly Forest Trees"]
        assert results[0]["source"].startswith("DEMO ONLY")


def test_limit_validation(engine):
    with open_session(engine) as session:
        with pytest.raises(CatalogError):
            search_resources(session, "any", limit=101)

