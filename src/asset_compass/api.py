"""Local REST API + MCP Streamable HTTP, both strictly read-only.

Starts on loopback by default; deployment, auth, rate limiting and TLS belong
to a later session. The catalog must first be initialized with `assetindex init`.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from . import __version__
from .mcp_server import mcp
from . import service


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Mounted MCP sub-apps don't run their own lifespan; the host must do it.
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="indexAI Asset Discovery API",
    description="Read-only discovery of curated 2D/3D asset links. Not a file mirror.",
    version=__version__,
    lifespan=lifespan,
)


def _call(operation, /, *args, not_found: bool = False, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=404 if not_found else 422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Catalog database unavailable; run assetindex init") from exc


@app.get("/healthz", tags=["Operations"])
async def healthz():
    """Check that the configured catalog tables can be queried."""
    return _call(service.catalog_health)


@app.get("/v1/assets/search", tags=["Discovery"])
async def search_assets(
    q: Annotated[str, Query(min_length=1, max_length=500, description="Natural-language asset search")],
    dimension: Literal["2d", "3d", "both"] | None = None,
    kind: str | None = None,
    tag: str | None = None,
    style: str | None = None,
    subject: str | None = None,
    format: str | None = None,
    access: Literal["free", "paid", "mixed", "unknown"] | None = None,
    license_id: str | None = None,
    license_status: Literal["unknown", "claimed", "verified"] | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    """Return approved indexed links with rank reasons and source fallback."""
    return _call(
        service.search_assets, q, dimension=dimension, kind=kind,
        tag=tag, style=style, subject=subject, format=format, access=access,
        license_id=license_id, license_status=license_status, limit=limit,
    )


@app.get("/v1/sources/search", tags=["Discovery"])
async def find_sources(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    dimension: Literal["2d", "3d", "both"] | None = None,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
):
    """Recommend curated source directories; no availability or rights guarantee."""
    return _call(service.search_sources, q, dimension=dimension, kind=kind, limit=limit)


@app.get("/v1/assets/{asset_id}", tags=["Discovery"])
async def get_asset(asset_id: int):
    """Get one approved asset or collection by its catalog ID."""
    return _call(service.get_asset, asset_id, not_found=True)


# Mount after REST routes. The SDK's default endpoint is /mcp, kept at the root.
# Its local-host DNS rebinding protections stay enabled; no permissive CORS.
app.mount("/", mcp.streamable_http_app(json_response=True, stateless_http=True))


def main() -> None:
    port = int(os.environ.get("ASSET_COMPASS_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("ASSET_COMPASS_PORT must be between 1 and 65535")
    uvicorn.run("asset_compass.api:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
