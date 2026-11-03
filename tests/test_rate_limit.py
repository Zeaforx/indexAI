"""HTTP request throttling covers REST and MCP without trusting spoofed headers."""

import asyncio

import httpx
import pytest
from starlette.responses import JSONResponse

from asset_compass.rate_limit import RateLimitGuard


async def success(scope, receive, send):
    await JSONResponse({"ok": True})(scope, receive, send)


def test_rate_limit_both_rest_and_mcp_and_resets_after_window():
    now = [100.0]
    guard = RateLimitGuard(success, max_requests=2, window_seconds=60, clock=lambda: now[0])

    async def scenario():
        transport = httpx.ASGITransport(app=guard, client=("203.0.113.2", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            assert (await client.get("/v1/assets/search?q=tree")).status_code == 200
            assert (await client.post("/mcp", json={})).status_code == 200
            response = await client.get("/v1/sources/search?q=tree")
            assert response.status_code == 429
            assert response.headers["Retry-After"] == "60"
            assert response.json()["detail"] == "Rate limit exceeded; retry later"
            assert response.headers["Cache-Control"] == "no-store"
            # /healthz is operational and remains outside the discovery quota.
            assert (await client.get("/healthz")).status_code == 200
            now[0] += 60
            assert (await client.get("/v1/assets/1")).status_code == 200

    asyncio.run(scenario())


def test_spoofed_forwarded_for_does_not_escape_quota():
    guard = RateLimitGuard(success, max_requests=1)

    async def scenario():
        transport = httpx.ASGITransport(app=guard, client=("192.0.2.10", 4000))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            assert (await client.get("/v1/assets/1", headers={"X-Forwarded-For": "1.1.1.1"})).status_code == 200
            assert (await client.get("/v1/assets/1", headers={"X-Forwarded-For": "2.2.2.2"})).status_code == 429

    asyncio.run(scenario())


def test_client_tracking_is_bounded():
    guard = RateLimitGuard(success, max_requests=2, max_clients=1)

    async def scenario():
        first = httpx.ASGITransport(app=guard, client=("192.0.2.1", 1))
        second = httpx.ASGITransport(app=guard, client=("192.0.2.2", 2))
        async with httpx.AsyncClient(transport=first, base_url="http://localhost") as first_client:
            assert (await first_client.get("/mcp")).status_code == 200
        async with httpx.AsyncClient(transport=second, base_url="http://localhost") as second_client:
            assert (await second_client.get("/mcp")).status_code == 429

    asyncio.run(scenario())


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        RateLimitGuard(success, max_requests=0)
    with pytest.raises(ValueError):
        RateLimitGuard(success, max_requests=1001)
