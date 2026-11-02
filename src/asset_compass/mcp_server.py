"""Read-only Model Context Protocol tools for agents seeking 2D/3D assets.

Local stdio: `assetindex-mcp`.
HTTP: mount the same MCPServer in `asset_compass.api` at `/mcp`.
"""

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.exc import SQLAlchemyError

from . import __version__
from . import service

mcp = MCPServer(
    "indexAI",
    version=__version__,
    instructions=(
        "Use search_assets to look up approved 2D/3D asset and collection links. "
        "When no asset matches, review the source-directory fallback. "
        "Never treat provider-claimed license metadata as independently verified. "
        "This server does not download assets or browse websites."
    ),
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _call(operation, /, *args, **kwargs):
    """Return agent-readable validation errors without leaking DB internals."""
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except SQLAlchemyError as exc:
        raise ToolError("Catalog database unavailable; run assetindex init") from exc


@mcp.tool(annotations=READ_ONLY)
async def search_assets(
    query: Annotated[str, Field(min_length=1, max_length=500, description="Description of the wanted 2D/3D game assets")],
    dimension: Literal["2d", "3d", "both"] | None = None,
    kind: str | None = None,
    tag: str | None = None,
    style: str | None = None,
    subject: str | None = None,
    format: str | None = None,
    access: Literal["free", "paid", "mixed", "unknown"] | None = None,
    license_id: str | None = None,
    license_status: Literal["unknown", "claimed", "verified"] | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    """Search approved, labeled 2D/3D links; return evidence and source fallback on no hit."""
    return _call(service.search_assets,
        query, dimension=dimension, kind=kind, tag=tag, style=style,
        subject=subject, format=format, access=access, license_id=license_id,
        license_status=license_status, limit=limit,
    )


@mcp.tool(annotations=READ_ONLY)
async def find_sources(
    query: Annotated[str, Field(min_length=1, max_length=500)],
    dimension: Literal["2d", "3d", "both"] | None = None,
    kind: str | None = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict[str, Any]:
    """Find curated asset directories without inventing an individual asset link."""
    return _call(service.search_sources, query, dimension=dimension, kind=kind, limit=limit)


@mcp.tool(annotations=READ_ONLY)
async def get_asset(asset_id: Annotated[int, Field(ge=1)]) -> dict[str, Any]:
    """Fetch one approved resource's tags, provenance, licensing and canonical URL."""
    return _call(service.get_asset, asset_id)


def main() -> None:
    """Start MCP over stdio for a local agent host."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
