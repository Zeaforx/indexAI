"""Shared read-only application service for REST and MCP clients.

This module intentionally exposes no curator mutations or SQL query execution.
It reads only the saved, approved catalog and returns source provenance intact.
"""

from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .catalog import CatalogError, find_sources, get_resource, search_resources
from .db import db_url, make_engine
from .models import Resource, Source, resource_dict

RIGHTS_NOTICE = (
    "Results are destination links, not asset downloads. License status 'claimed' "
    "is a provider claim, not independent verification. Check each source before use."
)


@lru_cache(maxsize=8)
def _engine_for(url: str):
    """Reuse connections across web requests while allowing isolated test databases."""
    return make_engine(url)


def _session() -> Session:
    return Session(_engine_for(db_url()))


def search_assets(
    query: str,
    *,
    dimension: str | None = None,
    kind: str | None = None,
    tag: str | None = None,
    style: str | None = None,
    subject: str | None = None,
    format: str | None = None,
    access: str | None = None,
    license_id: str | None = None,
    license_status: str | None = None,
    limit: int = 10,
    include_sources: bool = True,
) -> dict:
    """Return approved indexed links plus optional transparent source fallback."""
    if not query.strip():
        raise CatalogError("Query must not be empty")
    with _session() as session:
        items = search_resources(
            session, query, dimension=dimension, kind=kind, tag=tag,
            style=style, subject=subject, format=format, access=access,
            license_id=license_id, license_status=license_status,
            limit=limit,
        )
        routes = find_sources(session, query, dimension=dimension, kind=kind) if include_sources and not items else []
    return {
        "query": query,
        "count": len(items),
        "resources": items,
        "sources": routes,
        "fallback_used": bool(routes and not items),
        "rights_notice": RIGHTS_NOTICE,
    }


def search_sources(
    query: str, *, dimension: str | None = None, kind: str | None = None,
    limit: int = 5,
) -> dict:
    """Recommend browsable source directories without asserting asset existence."""
    if not query.strip():
        raise CatalogError("Query must not be empty")
    with _session() as session:
        routes = find_sources(session, query, dimension=dimension, kind=kind, limit=limit)
    return {"query": query, "count": len(routes), "sources": routes, "rights_notice": RIGHTS_NOTICE}


def get_asset(asset_id: int) -> dict:
    """Read one approved resource. Pending/rejected resources are not exposed."""
    if asset_id < 1:
        raise CatalogError("No approved asset found")
    with _session() as session:
        try:
            resource = get_resource(session, asset_id)
        except CatalogError as exc:
            raise CatalogError("No approved asset found") from exc
        if resource.review_status != "approved":
            raise CatalogError("No approved asset found")
        item = resource_dict(resource)
    return {"resource": item, "rights_notice": RIGHTS_NOTICE}


def catalog_health() -> dict:
    """Only a readiness check: does the configured database contain the tables?"""
    with _session() as session:
        resources = session.scalar(select(func.count()).select_from(Resource))
        sources = session.scalar(select(func.count()).select_from(Source))
    return {"status": "ok", "resources": resources, "sources": sources}
