"""Link observations should be conservative, opt-in, and never alter curation."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from typer.testing import CliRunner

from asset_compass.cli import app
from asset_compass.db import initialize, make_engine, open_session
from asset_compass.ingestion.batch import import_records
from asset_compass.link_health import Probe, _classify, _safe_host, check_links, probe_url
from asset_compass.models import Resource


def records():
    return [
        {"source_name": "Kenney", "source_url": "https://kenney.nl", "url": "https://kenney.nl/assets/old-pack", "title": "Old Pack", "dimension": "2d", "kind": "sprite", "review_status": "approved", "review_method": "ai-assisted"},
        {"source_name": "Kenney", "source_url": "https://kenney.nl", "url": "https://kenney.nl/assets/new-pack", "title": "New Pack", "dimension": "2d", "kind": "sprite", "review_status": "approved", "review_method": "ai-assisted"},
        {"source_name": "Other", "source_url": "https://example.org", "url": "https://example.org/assets/model", "title": "Other Pack", "dimension": "3d", "kind": "model", "review_status": "approved", "review_method": "human"},
    ]


def test_host_allowlist_disallows_arbitrary_external_requests():
    for unsafe in (
        "http://kenney.nl/assets/pack", "https://notkenney.nl/assets/pack",
        "https://kenney.nl.evil.test/assets/pack", "https://kenney.nl:8443/assets/pack",
        "https://u:p@kenney.nl/assets/pack", "https://kenney.nl:bad/assets/pack",
        "https://127.0.0.1/assets/pack",
    ):
        assert not _safe_host(unsafe)[0], unsafe
    assert _safe_host("https://kenney.nl/assets/pack")[0]


def test_response_classification_never_claims_missing_is_confirmed():
    assert _classify(200).status == "healthy"
    assert _classify(404).status == "suspect_missing"
    assert "manual" in _classify(410).note
    assert _classify(429).status == "restricted"
    assert _classify(405).status == "unsupported"
    assert _classify(301).status == "redirect"
    assert _classify(502).status == "transient_error"


def test_probe_is_head_only_and_never_follows_redirects(monkeypatch):
    from asset_compass import link_health

    monkeypatch.setattr(link_health, "_public_addresses", lambda host: True)

    class FakeOpener:
        def open(self, request, timeout):
            assert request.get_method() == "HEAD"
            assert timeout == 6.0
            raise link_health.HTTPError(request.full_url, 301, "Moved", {}, None)

    def opener(*handlers):
        assert link_health.NoRedirect in handlers
        return FakeOpener()

    monkeypatch.setattr(link_health, "build_opener", opener)
    result = probe_url("https://kenney.nl/assets/old-pack")
    assert result.status == "redirect" and result.http_status == 301
    assert probe_url("https://example.org/private").status == "skipped"
    monkeypatch.setattr(link_health, "_public_addresses", lambda host: False)
    assert probe_url("https://kenney.nl/assets/old-pack").status == "skipped"


def test_checker_preview_execute_cooldown_and_review_preservation(engine):
    with open_session(engine) as session:
        assert import_records(session, records())["created"] == 3
        fetched = []

        def fake_checker(url):
            fetched.append(url)
            return Probe("suspect_missing", 404, "HEAD suggests missing; manually confirm")

        preview = check_links(session, limit=3, checker=fake_checker, pause_seconds=0)
        assert preview["mode"] == "preview" and preview["checked"] == 0
        assert preview["skipped"] == 1
        assert not fetched
        executed = check_links(session, limit=3, execute=True, checker=fake_checker, pause_seconds=0)
        assert executed["checked"] == 2
        assert executed["skipped"] == 1
        assert len(fetched) == 2

    with open_session(engine) as session:
        for item in session.scalars(select(Resource).where(Resource.source_id == 1)):
            assert item.url_status == "suspect_missing" and item.last_http_status == 404
            assert item.review_status == "approved" and item.last_checked_at is not None
        assert session.scalar(select(Resource).where(Resource.source_id == 2)).url_status == "unknown"

        def fail_if_network(url):
            raise AssertionError("Cooldown should prevent a network request")

        cooldown = check_links(session, limit=2, source_name="Kenney", execute=True, checker=fail_if_network, pause_seconds=0)
        assert cooldown["checked"] == 0 and cooldown["skipped"] == 2
        forced = check_links(session, limit=2, source_name="Kenney", execute=True, force=True,
                             checker=lambda url: Probe("healthy", 200, "okay"), pause_seconds=0)
        assert forced["checked"] == 2
        assert all(item.url_status == "healthy" for item in session.scalars(select(Resource).where(Resource.source_id == 1)))


def test_checker_source_filter_limits_and_cli_preview(tmp_path, monkeypatch):
    db_file = tmp_path / "links.sqlite3"
    monkeypatch.setenv("ASSET_COMPASS_DB_URL", f"sqlite:///{db_file}")
    engine = make_engine(f"sqlite:///{db_file}")
    initialize(engine)
    with open_session(engine) as session:
        import_records(session, records())
        scoped = check_links(session, limit=1, source_name="other")
        assert scoped["results"][0]["status"] == "skipped"
    cli = CliRunner()
    response = cli.invoke(app, ["check-links", "--limit", "3"])
    assert response.exit_code == 0, response.output
    assert '"mode": "preview"' in response.output
    assert cli.invoke(app, ["check-links", "--force"]).exit_code == 1
    assert cli.invoke(app, ["check-links", "--limit", "21"]).exit_code == 1
    engine.dispose()


def test_migration_from_previous_schema_adds_observation_fields(tmp_path):
    from pathlib import Path
    import asset_compass

    engine = make_engine(f"sqlite:///{tmp_path / 'previous.sqlite3'}")
    config = Config()
    config.set_main_option("script_location", str(Path(asset_compass.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003")
    before = {c["name"] for c in inspect(engine).get_columns("resources")}
    assert "last_checked_at" not in before
    initialize(engine)
    after = {c["name"] for c in inspect(engine).get_columns("resources")}
    assert {"last_checked_at", "last_http_status"}.issubset(after)
    engine.dispose()
