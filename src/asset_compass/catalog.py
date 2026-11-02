"""Catalog commands, invariants and the first deterministic search implementation."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Resource, Source, Tag, resource_dict
from .taxonomy import (
    ACCESS_TYPES, DIMENSIONS, KINDS, LICENSE_STATUSES, REVIEW_METHODS,
    REVIEW_STATUSES, normalize_tag, parse_formats, parse_tags, require_choice,
)
from .urls import canonicalize_url


class CatalogError(ValueError):
    """A validation or missing-record error that can be shown to a curator."""


def add_source(
    session: Session,
    url: str,
    name: str,
    description: str = "",
    policy_url: str | None = None,
    ingestion_method: str = "manual",
    attribution_notice: str = "",
) -> tuple[Source, bool]:
    if not name.strip():
        raise CatalogError("Source name cannot be empty")
    if ingestion_method not in {"manual", "official_api", "import"}:
        raise CatalogError("Unsupported source ingestion method")
    normalized = canonicalize_url(url)
    existing = session.scalar(select(Source).where(Source.canonical_url == normalized))
    if existing:
        return existing, False
    source = Source(
        canonical_url=normalized,
        name=name.strip(),
        description=description.strip(),
        policy_url=canonicalize_url(policy_url) if policy_url else None,
        ingestion_method=ingestion_method,
        attribution_notice=attribution_notice.strip(),
    )
    session.add(source)
    session.flush()
    return source, True


def list_sources(session: Session) -> list[Source]:
    return list(session.scalars(select(Source).order_by(Source.name, Source.id)))


def get_resource(session: Session, resource_id: int) -> Resource:
    resource = session.scalar(
        select(Resource)
        .options(selectinload(Resource.source), selectinload(Resource.tags))
        .where(Resource.id == resource_id)
    )
    if not resource:
        raise CatalogError(f"Resource #{resource_id} does not exist")
    return resource


def _get_tags(session: Session, names: list[str]) -> list[Tag]:
    result = []
    for name in names:
        tag = session.scalar(select(Tag).where(Tag.slug == name))
        if tag is None:
            tag = Tag(slug=name)
            session.add(tag)
            session.flush()
        result.append(tag)
    return result


def _license_check(status: str, license_id: str | None, license_url: str | None) -> None:
    if status == "verified" and (not license_id or not license_url):
        raise CatalogError("Verified licenses require both --license and --license-url evidence")


def add_resource(
    session: Session,
    *,
    url: str,
    source_id: int,
    title: str,
    dimension: str,
    kind: str,
    description: str = "",
    tags: str = "",
    formats: str = "",
    access: str = "unknown",
    license_id: str | None = None,
    license_url: str | None = None,
    license_status: str = "unknown",
    record_type: str = "asset",
    author_name: str = "",
    source_asset_id: str | None = None,
    source_tags: list[str] | None = None,
    metadata_source: str = "manual",
) -> tuple[Resource, bool]:
    if not title.strip():
        raise CatalogError("Resource title cannot be empty")
    dimension = require_choice(dimension, DIMENSIONS, "dimension")
    kind = require_choice(kind, KINDS, "kind")
    access = require_choice(access, ACCESS_TYPES, "access")
    license_status = require_choice(license_status, LICENSE_STATUSES, "license status")
    if record_type not in {"asset", "collection"}:
        raise CatalogError("Record type must be 'asset' or 'collection'")
    if metadata_source not in {"manual", "official_api", "batch_import"}:
        raise CatalogError("Unsupported resource metadata source")
    evidence = canonicalize_url(license_url) if license_url else None
    _license_check(license_status, license_id, evidence)
    canonical = canonicalize_url(url)
    source = session.get(Source, source_id)
    if source is None:
        raise CatalogError(f"Source #{source_id} does not exist; add it first")
    existing = session.scalar(select(Resource).where(Resource.canonical_url == canonical))
    if existing:
        return get_resource(session, existing.id), False

    resource = Resource(
        canonical_url=canonical,
        source=source,
        title=title.strip(),
        description=description.strip(),
        dimension=dimension,
        kind=kind,
        formats=parse_formats(formats),
        access_type=access,
        license_id=license_id,
        license_url=evidence,
        license_status=license_status,
        record_type=record_type,
        author_name=author_name.strip(),
        source_asset_id=source_asset_id,
        source_tags=source_tags or [],
        metadata_source=metadata_source,
    )
    session.add(resource)
    resource.tags = _get_tags(session, parse_tags(tags))
    session.flush()
    return resource, True


def annotate_resource(
    session: Session,
    resource_id: int,
    *,
    tags: str | None = None,
    description: str | None = None,
    formats: str | None = None,
    access: str | None = None,
    license_id: str | None = None,
    license_url: str | None = None,
    license_status: str | None = None,
) -> Resource:
    resource = get_resource(session, resource_id)
    if tags is not None:
        resource.tags = _get_tags(session, parse_tags(tags))
    if formats is not None:
        resource.formats = parse_formats(formats)
    if description is not None:
        resource.description = description.strip()
    if access is not None:
        resource.access_type = require_choice(access, ACCESS_TYPES, "access")
    new_license_status = (
        require_choice(license_status, LICENSE_STATUSES, "license status")
        if license_status else resource.license_status
    )
    new_license_id = license_id if license_id is not None else resource.license_id
    new_license_url = canonicalize_url(license_url) if license_url else resource.license_url
    _license_check(new_license_status, new_license_id, new_license_url)
    resource.license_status = new_license_status
    resource.license_id = new_license_id
    resource.license_url = new_license_url
    session.flush()
    return resource


def review_resource(
    session: Session,
    resource_id: int,
    *,
    status: str,
    method: str,
    note: str = "",
) -> Resource:
    status = require_choice(status, REVIEW_STATUSES, "review status")
    method = require_choice(method, REVIEW_METHODS, "review method")
    if status == "approved" and method == "none":
        raise CatalogError("Approved records must declare their review method")
    resource = get_resource(session, resource_id)
    resource.review_status = status
    resource.review_method = method
    resource.review_note = note.strip()
    session.flush()
    return resource


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def search_resources(
    session: Session,
    query: str,
    *,
    dimension: str | None = None,
    kind: str | None = None,
    tag: str | None = None,
    access: str | None = None,
    include_pending: bool = False,
    limit: int = 10,
) -> list[dict]:
    """Small-catalog search. Session 3 replaces this with PostgreSQL FTS."""
    if not 1 <= limit <= 100:
        raise CatalogError("Limit must be between 1 and 100")
    if dimension:
        dimension = require_choice(dimension, DIMENSIONS, "dimension")
    if kind:
        kind = require_choice(kind, KINDS, "kind")
    if access:
        access = require_choice(access, ACCESS_TYPES, "access")
    tag = normalize_tag(tag) if tag else None
    statement = select(Resource).options(
        selectinload(Resource.source), selectinload(Resource.tags)
    )
    if not include_pending:
        statement = statement.where(Resource.review_status == "approved")
    if dimension and dimension != "both":
        statement = statement.where(Resource.dimension.in_((dimension, "both")))
    if kind:
        statement = statement.where(Resource.kind == kind)
    if access:
        statement = statement.where(Resource.access_type == access)

    query_words = _words(query)
    scored = []
    for resource in session.scalars(statement):
        tags = {item.slug for item in resource.tags}
        if tag and tag not in tags:
            continue
        title_words = _words(resource.title)
        tag_words = _words(" ".join(tags))
        description_words = _words(resource.description)
        score = (
            4 * len(query_words & title_words)
            + 3 * len(query_words & tag_words)
            + len(query_words & description_words)
        )
        if query_words and score == 0:
            continue
        data = resource_dict(resource)
        data["score"] = score
        scored.append(data)
    scored.sort(key=lambda item: (-item["score"], item["title"].casefold(), item["id"]))
    return scored[:limit]

