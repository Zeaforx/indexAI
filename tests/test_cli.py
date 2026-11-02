import json

from typer.testing import CliRunner

from asset_compass.cli import app
from pathlib import Path

runner = CliRunner()


def test_cli_end_to_end(tmp_path, monkeypatch):
    db_file = tmp_path / "catalog.sqlite3"
    monkeypatch.setenv("ASSET_COMPASS_DB_URL", f"sqlite:///{db_file}")
    assert runner.invoke(app, ["init"]).exit_code == 0
    source = runner.invoke(app, ["source", "add", "https://example.org", "--name", "Demo"])
    assert source.exit_code == 0, source.output
    assert "source #1" in source.output
    resource = runner.invoke(app, [
        "resource", "add", "https://example.org/assets/tree", "--source", "1",
        "--title", "Low Poly Tree", "--dimension", "3d", "--kind", "model",
        "--tags", "low poly,tree", "--formats", "gltf",
    ])
    assert resource.exit_code == 0, resource.output
    assert "pending review" in resource.output
    assert "No matching" in runner.invoke(app, ["search", "tree"]).output
    annotate = runner.invoke(app, ["resource", "annotate", "1", "--tags", "lowpoly,forest,tree"])
    assert annotate.exit_code == 0, annotate.output
    approve = runner.invoke(app, ["resource", "review", "1", "--status", "approved", "--method", "ai-assisted"])
    assert approve.exit_code == 0, approve.output
    response = runner.invoke(app, ["search", "low poly tree", "--dimension", "3d", "--json"])
    assert response.exit_code == 0, response.output
    results = json.loads(response.output)
    assert len(results) == 1 and results[0]["id"] == 1
    assert results[0]["tags"] == ["forest", "low-poly", "tree"]
    assert db_file.exists()


def test_cli_handles_bad_records(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_COMPASS_DB_URL", f"sqlite:///{tmp_path / 'bad.sqlite3'}")
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["resource", "add", "https://example.org/a", "--source", "999", "--title", "X", "--dimension", "3d", "--kind", "model"])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_cli_session3_search_and_source_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_COMPASS_DB_URL", f"sqlite:///{tmp_path / 'session3.sqlite3'}")
    assert runner.invoke(app, ["init"]).exit_code == 0
    kenney = Path(__file__).resolve().parents[1] / "data" / "seed_kenney.json"
    ingest = runner.invoke(app, ["ingest", "file", str(kenney)])
    assert ingest.exit_code == 0, ingest.output
    search = runner.invoke(app, ["search", "2d pixel art platformer", "--style", "pixel-art", "--license-status", "claimed", "--json"])
    assert search.exit_code == 0, search.output
    assert json.loads(search.output)[0]["license"]["status"] == "claimed"
    strict = runner.invoke(app, ["search", "pixel platformer", "--format", "png", "--with-sources", "--json"])
    assert strict.exit_code == 0, strict.output
    payload = json.loads(strict.output)
    assert payload["resources"] == []
    assert payload["sources"][0]["name"] == "Kenney"
    fallback = runner.invoke(app, ["find-sources", "2d zombie sprites", "--json"])
    assert fallback.exit_code == 0, fallback.output
    assert json.loads(fallback.output)[0]["browse_url"] == "https://kenney.nl/assets"

