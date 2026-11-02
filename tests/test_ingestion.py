import json

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select

from asset_compass.db import initialize, make_engine, open_session
from asset_compass.ingestion.batch import export_records, import_records, load_records
from asset_compass.ingestion.polyhaven import Candidate, IngestionError, select_models
from asset_compass.models import Resource, Source


def sample_listing():
    return {
        "OldTree_01": {"type": 2, "name": "Old Tree", "description": "Ancient oak 3D model", "tags": ["tree", "forest"], "categories": ["nature"], "category": "Nature/Trees", "authors": {"Artist A": "All"}},
        "Chair_01": {"type": 2, "name": "Vintage Chair", "description": "Interior seat", "tags": ["chair", "classic"], "categories": ["furniture"], "category": "Furniture/Seating", "authors": {"Artist B": "All"}},
        "Rock_01": {"type": 2, "name": "Rock", "description": "Stone for fantasy game", "tags": ["stone", "terrain"], "categories": ["nature"], "category": "Nature/Rocks"},
        "Texture_01": {"type": 1, "name": "Not a Model", "tags": ["texture"]},
        "../unsafe": {"type": 2, "name": "Invalid ID"},
    }


def test_polyhaven_parsing_has_source_and_diverse_categories():
    rows = select_models(sample_listing(), limit=3)
    assert len(rows) == 3
    assert all(isinstance(row, Candidate) for row in rows)
    assert {row.title for row in rows} == {"Old Tree", "Vintage Chair", "Rock"}
    assert all(row.license_status == "claimed" and row.license_id == "CC0-1.0" for row in rows)
    assert all(row.source_name == "Poly Haven" and row.metadata_source == "official_api" for row in rows)
    assert all(row.formats == [] for row in rows)  # no invented file formats
    assert rows[0].url.startswith("https://polyhaven.com/a/")
    assert [r.title for r in select_models(sample_listing(), limit=3, query="chair")] == ["Vintage Chair"]


def test_polyhaven_rejects_invalid_limit():
    try:
        select_models(sample_listing(), limit=300)
        assert False, "Expected invalid limit"
    except ValueError:
        pass


def test_batch_dry_run_idempotent_and_partial_invalid(engine):
    rows = [c.as_import_record() for c in select_models(sample_listing(), limit=3)]
    bad = dict(rows[0]); bad.update(url="https://polyhaven.com/a/bad", dimension="5d")
    with open_session(engine) as session:
        result = import_records(session, rows + [bad], dry_run=True)
        assert result["valid_new"] == 3
        assert result["created"] == 0
        assert len(result["errors"]) == 1
    with open_session(engine) as session:
        assert session.scalar(select(Resource)) is None
        report = import_records(session, rows + [bad])
        assert report["created"] == 3
        assert len(report["errors"]) == 1
    with open_session(engine) as session:
        assert len(list(session.scalars(select(Resource)))) == 3
        assert len(list(session.scalars(select(Source)))) == 1
        assert import_records(session, rows)["existing"] == 3
        resource = session.scalar(select(Resource).where(Resource.title == "Old Tree"))
        assert resource.review_status == "approved"
        assert resource.review_method == "automated"
        assert resource.source_asset_id == "OldTree_01"
        assert resource.source.ingestion_method == "official_api"
        assert resource.source.attribution_notice == "Powered by Poly Haven"


def test_manual_records_default_pending(engine):
    row = {
        "source_url": "https://kenney.nl", "source_name": "Kenney",
        "url": "https://kenney.nl/assets/pixel-platformer", "title": "Pixel Platformer",
        "dimension": "2d", "kind": "collection", "tags": ["pixel-art", "platformer"],
        "license_id": "CC0-1.0", "license_url": "https://kenney.nl/assets/pixel-platformer",
        "license_status": "claimed", "record_type": "collection",
    }
    with open_session(engine) as session:
        assert import_records(session, [row])["created"] == 1
    with open_session(engine) as session:
        resource = session.scalar(select(Resource))
        assert resource.review_status == "pending"
        assert resource.metadata_source == "batch_import"


def test_export_is_minimal_and_roundtrips(engine):
    rows = [c.as_import_record() for c in select_models(sample_listing(), limit=3)]
    with open_session(engine) as session:
        import_records(session, rows)
    with open_session(engine) as session:
        export = export_records(session, source_name="Poly Haven")
        assert len(export["records"]) == 3
        assert all(not x["description"] for x in export["records"])
        assert all("thumbnail_url" not in x for x in export["records"])
        assert export_records(session, source_name="Missing")["records"] == []
    other = make_engine("sqlite+pysqlite:///:memory:")
    initialize(other)
    with open_session(other) as session:
        assert import_records(session, export["records"])["created"] == 3
    other.dispose()


def test_load_json_and_csv(tmp_path):
    records = [{"source_url": "https://example.org", "source_name": "Example", "url": "https://example.org/a", "title": "A", "dimension": "2d", "kind": "sprite"}]
    path = tmp_path / "seed.json"
    path.write_text(json.dumps({"records": records}), encoding="utf-8")
    assert load_records(path) == records
    csv_file = tmp_path / "seed.csv"
    csv_file.write_text("source_url,source_name,url,title,dimension,kind\nhttps://example.org,Example,https://example.org/a,A,2d,sprite\n", encoding="utf-8")
    assert load_records(csv_file)[0]["kind"] == "sprite"


def test_dry_run_counts_same_url_once(engine):
    row = {
        "source_url": "https://example.org", "source_name": "Example",
        "url": "https://example.org/packs/one", "title": "One Pack",
        "dimension": "2d", "kind": "collection",
    }
    with open_session(engine) as session:
        report = import_records(session, [row, {**row, "url": row["url"] + "#section"}], dry_run=True)
    assert report["valid_new"] == 1
    assert report["existing"] == 1


def test_upgrade_from_session1_schema(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'old.sqlite3'}")
    config = Config()
    from pathlib import Path
    import asset_compass
    config.set_main_option("script_location", str(Path(asset_compass.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
    assert "source_asset_id" not in {c["name"] for c in inspect(engine).get_columns("resources")}
    initialize(engine)
    assert "source_asset_id" in {c["name"] for c in inspect(engine).get_columns("resources")}
    engine.dispose()

