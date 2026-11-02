"""Session 4 end-to-end tests for REST, shared service and actual MCP stdio."""

import asyncio

import httpx
import pytest

from asset_compass.api import app
from asset_compass.mcp_server import main as mcp_main, mcp
from asset_compass.catalog import CatalogError, add_resource, add_source
from asset_compass.db import initialize, make_engine, open_session
from asset_compass.ingestion.batch import import_records, load_records
from asset_compass.service import get_asset, search_assets, search_sources


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    """Real 2D/3D catalog plus a pending record that agents must never see."""
    db_file = tmp_path / "agent_catalog.sqlite3"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("ASSET_COMPASS_DB_URL", url)
    engine = make_engine(url)
    initialize(engine)
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    with open_session(engine) as session:
        assert import_records(session, load_records(root / "data/seed_kenney.json"))["created"] == 10
        assert import_records(session, load_records(root / "data/seed_polyhaven.json"))["created"] == 35
        source, _ = add_source(session, "https://example.org", "Unreviewed Source")
        resource, _ = add_resource(session, source_id=source.id, url="https://example.org/private",
                                   title="Private Zombie Sprite", dimension="2d", kind="sprite")
        pending_id = resource.id
    yield url, pending_id
    engine.dispose()


def test_shared_service_preserves_rights_and_filters(catalog):
    _url, pending_id = catalog
    results = search_assets("2d pixel platformer", dimension="2d", license_status="claimed")
    assert results["resources"]
    first = results["resources"][0]
    assert first["source"] == "Kenney"
    assert first["source_url"] == "https://kenney.nl/"
    assert first["source_policy_url"] == "https://kenney.nl/support"
    assert first["license"]["status"] == "claimed"
    assert first["review_status"] == "approved"
    assert first["match_reasons"]
    assert not results["fallback_used"]
    assert search_assets("pixel platformer", format="png")["resources"] == []

    missing = search_assets("3d flying dragon animation")
    assert missing["resources"] == [] and missing["fallback_used"]
    assert missing["sources"][0]["name"] == "Poly Haven"
    assert missing["sources"][0]["indexed_matches"] == 0
    assert "claimed" in missing["rights_notice"]
    assert search_sources("2d zombie sprites")["sources"][0]["name"] == "Kenney"

    with pytest.raises(CatalogError, match="No approved"):
        get_asset(pending_id)
    with pytest.raises(CatalogError, match="empty"):
        search_assets("   ")


def test_rest_search_source_detail_validation_and_read_only(catalog):
    _url, pending_id = catalog
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
            await check(client)

    async def check(client):
        readiness = await client.get("/healthz")
        assert readiness.status_code == 200 and readiness.json()["resources"] == 46
        response = await client.get("/v1/assets/search", params={"q": "3d old binoculars", "limit": 3})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["resources"][0]["title"] == "Binoculars"
        item_id = data["resources"][0]["id"]
        detail = await client.get(f"/v1/assets/{item_id}")
        assert detail.status_code == 200 and detail.json()["resource"]["id"] == item_id
        assert (await client.get(f"/v1/assets/{pending_id}")).status_code == 404
        assert (await client.get("/v1/assets/999999")).status_code == 404

        fallback = await client.get("/v1/assets/search", params={"q": "2d zombie sprites"})
        assert fallback.status_code == 200
        assert fallback.json()["resources"] == []
        assert fallback.json()["sources"][0]["browse_url"] == "https://kenney.nl/assets"
        assert (await client.get("/v1/sources/search", params={"q": "3d flying dragon"})).json()["sources"][0]["name"] == "Poly Haven"
        assert (await client.get("/v1/assets/search", params={"q": "forest", "limit": 999})).status_code == 422
        assert (await client.get("/v1/assets/search")).status_code == 422
        assert (await client.get("/v1/assets/search", params={"q": "forest", "kind": "invalid"})).status_code == 422
        assert (await client.post("/v1/assets/search", json={"q": "forest"})).status_code >= 400
        assert "/v1/assets/search" in (await client.get("/openapi.json")).json()["paths"]
    asyncio.run(scenario())


def test_rest_database_unavailable_returns_no_connection_details(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_COMPASS_DB_URL", f"sqlite:///{tmp_path / 'uninitialized.sqlite3'}")
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
            response = await client.get("/healthz")
            assert response.status_code == 503
            assert "unavailable" in response.json()["detail"]
            assert "sqlite" not in response.json()["detail"].casefold()
    asyncio.run(scenario())


def test_mcp_stdio_entrypoint_configures_official_transport(monkeypatch):
    """Stdio startup configuration; end-to-end MCP is covered over HTTP below."""
    called = []
    monkeypatch.setattr(mcp, "run", lambda **kwargs: called.append(kwargs))
    mcp_main()
    assert called == [{"transport": "stdio"}]


def test_http_mcp_jsonrpc_tool_listing(catalog):
    """Exercise actual Streamable HTTP protocol, not only the decorator functions."""
    async def scenario():
        async with mcp.session_manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
                await check(client)

    async def check(client):
        headers = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
        initialization = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "indexai-test", "version": "1.0"},
            },
        }, headers=headers)
        assert initialization.status_code == 200, initialization.text
        assert initialization.json()["result"]["serverInfo"]["name"] == "indexAI"
        listing = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, headers=headers)
        assert listing.status_code == 200, listing.text
        tools = listing.json()["result"]["tools"]
        names = {tool["name"] for tool in tools}
        assert names == {"search_assets", "find_sources", "get_asset"}
        assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
        call = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "search_assets", "arguments": {"query": "3d binoculars"},
        }}, headers=headers)
        assert call.status_code == 200, call.text
        result = call.json()["result"]
        assert result["structuredContent"]["resources"][0]["title"] == "Binoculars"
        route = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "find_sources", "arguments": {"query": "2d zombie sprites"},
        }}, headers=headers)
        assert route.json()["result"]["structuredContent"]["sources"][0]["name"] == "Kenney"
        denied = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
            "name": "get_asset", "arguments": {"asset_id": 46},
        }}, headers=headers)
        assert denied.json()["result"]["isError"] is True
        bad = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {
            "name": "search_assets", "arguments": {"query": "forest", "limit": 10000},
        }}, headers=headers)
        assert bad.json()["result"]["isError"] is True
    asyncio.run(scenario())
