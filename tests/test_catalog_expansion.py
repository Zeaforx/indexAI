"""Session 5: official-API adapters, offline snapshots, and expanded retrieval."""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from asset_compass.catalog import find_sources, search_resources
from asset_compass.db import open_session
from asset_compass.ingestion import ambientcg, polyhaven
from asset_compass.ingestion.batch import import_records, load_records
from asset_compass.models import Resource, Source


DATA = Path(__file__).resolve().parents[1] / "data"
SEEDS = (
    "seed_kenney.json", "seed_polyhaven.json", "seed_kenney_expansion.json",
    "seed_ambientcg_materials.json", "seed_polyhaven_textures.json",
)


def test_polyhaven_texture_and_hdri_selection():
    listing = {
        "old_model": {"type": 2, "name": "Vintage Car", "tags": ["vehicle"]},
        "stone_floor": {"type": 1, "name": "Stone Floor", "tags": ["stone"], "category": "Floor/Stone"},
        "sky_01": {"type": 0, "name": "Sunset Sky", "tags": ["sunset"], "category": "Outdoor/Sky"},
        "../unsafe": {"type": 1, "name": "Invalid"},
    }
    textures = polyhaven.select_assets(listing, asset_type="textures", limit=2)
    assert len(textures) == 1
    assert textures[0].kind == "texture"
    assert {"pbr", "material", "stone"}.issubset(textures[0].tags)
    assert textures[0].formats == []
    hdris = polyhaven.select_assets(listing, asset_type="hdris")
    assert len(hdris) == 1 and hdris[0].kind == "environment"
    assert "hdri" in hdris[0].tags and hdris[0].url.endswith("/sky_01")
    with pytest.raises(ValueError):
        polyhaven.select_assets(listing, asset_type="unsupported")


def test_ambientcg_selects_diverse_families_and_rejects_invalid_rows():
    listing = {"assets": [
        {"id": "Bricks001", "type": "material", "title": "Bricks 001", "tags": ["red bricks"]},
        {"id": "Bricks002", "type": "material", "title": "Bricks 002", "tags": ["wall"]},
        {"id": "Grass001", "type": "material", "title": "Grass 001", "tags": ["grass"]},
        {"id": "invalid!", "type": "material", "title": "Bad"},
        {"id": "Bricks001", "type": "material", "title": "Duplicate"},
        {"id": "Sky001", "type": "hdri", "title": "Sky"},
    ]}
    selected = ambientcg.select_assets(listing, limit=2)
    assert {x.source_asset_id for x in selected} == {"Bricks001", "Grass001"}
    assert all(x.url.startswith("https://ambientcg.com/a/") for x in selected)
    assert all(x.kind == "texture" and x.dimension == "3d" for x in selected)
    assert all(x.license_status == "claimed" and x.formats == [] for x in selected)
    hdri = ambientcg.select_assets(listing, asset_type="hdri", limit=2)
    assert len(hdri) == 1 and hdri[0].kind == "environment"
    assert {"hdri", "skybox", "lighting"}.issubset(hdri[0].tags)
    with pytest.raises(ambientcg.AmbientCGError):
        ambientcg.select_assets({"unexpected": []})
    with pytest.raises(ValueError):
        ambientcg.select_assets(listing, limit=81)


def test_ambientcg_fetch_uses_one_capped_official_api_page(monkeypatch):
    requested = []

    class Response:
        headers = {"Content-Length": "33"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, number):
            assert number == ambientcg.MAX_RESPONSE_BYTES + 1
            return b'{"assets": [], "nextCursor": null}'

    def fake_urlopen(request, timeout):
        requested.append(request)
        assert timeout == 20.0
        return Response()

    monkeypatch.setattr(ambientcg, "urlopen", fake_urlopen)
    assert ambientcg.fetch_listing(asset_type="3d-model", limit=12, query="stone")["assets"] == []
    assert len(requested) == 1
    assert requested[0].full_url.startswith("https://ambientcg.com/api/v3/assets?")
    assert "type=3d-model" in requested[0].full_url
    assert "q=stone" in requested[0].full_url
    assert "indexAI" in requested[0].get_header("User-agent")
    with pytest.raises(ValueError):
        ambientcg.fetch_listing(asset_type="all")
    with pytest.raises(ValueError):
        ambientcg.fetch_listing(query="x" * 101)


def test_polyhaven_fetch_typed_official_api(monkeypatch):
    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            assert size == polyhaven.MAX_RESPONSE_BYTES + 1
            return b"{}"

    def fake_fetch(req, timeout):
        assert req.full_url == "https://api.polyhaven.com/assets?t=textures"
        return Response()

    monkeypatch.setattr(polyhaven, "urlopen", fake_fetch)
    assert polyhaven.fetch_listing(asset_type="textures") == {}
    with pytest.raises(ValueError):
        polyhaven.fetch_listing(asset_type="materials")


def test_all_110_seed_records_import_idempotently_and_find_matches(engine):
    counts = [10, 35, 17, 30, 18]
    with open_session(engine) as session:
        for file, count in zip(SEEDS, counts):
            rows = load_records(DATA / file)
            assert len(rows) == count
            report = import_records(session, rows)
            assert report["created"] == count, (file, report)
            assert report["errors"] == []
        assert session.scalar(select(func.count(Resource.id))) == sum(counts)
        assert session.scalar(select(func.count(Source.id))) == 3

    with open_session(engine) as session:
        for file, count in zip(SEEDS, counts):
            again = import_records(session, load_records(DATA / file))
            assert again["existing"] == count and again["created"] == 0
        wood = search_resources(session, "3d PBR wood floor parquet texture", dimension="3d")
        assert "Wood Floor 051" in [x["title"] for x in wood[:5]]
        assert all(x["license"]["status"] == "claimed" for x in wood)
        exact_format = search_resources(session, "gamepad input prompts", format="svg")
        assert [x["title"] for x in exact_format] == ["Input Prompts"]
        assert search_resources(session, "flying dragon animations", dimension="3d") == []
        sources = find_sources(session, "3d flying dragon animations", dimension="3d")
        assert sources[0]["name"] == "Kenney"
        assert sources[0]["match_basis"] == "kind and dimension coverage"
        pbr = find_sources(session, "3d PBR metal texture", dimension="3d")
        assert pbr[0]["browse_url"] in {"https://polyhaven.com/textures", "https://ambientcg.com/list"}
        ambient = session.scalar(select(Source).where(Source.name == "ambientCG"))
        assert ambient.attribution_notice == "Assets from ambientCG"
        assert all(
            row.review_status == "approved" and row.license_status == "claimed"
            for row in session.scalars(select(Resource))
        )


def test_expanded_benchmark_is_reproducible_in_fresh_database(engine):
    from asset_compass.evaluation import run_evaluation

    with open_session(engine) as session:
        for file in SEEDS:
            assert import_records(session, load_records(DATA / file))["errors"] == []
    with open_session(engine) as session:
        cases = json.loads((DATA / "evaluation_queries_expanded.json").read_text())["cases"]
        report = run_evaluation(session, cases)
        assert report["cases"] == 32
        assert report["passed"] == 32, [d for d in report["details"] if not d["passed"]]
