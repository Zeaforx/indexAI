"""Catalog commands, provenance validation and searchable asset/source routes."""

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import Session, selectinload

from .models import Resource, Source, Tag, resource_dict
from .relevance import infer_dimension, query_terms, rarity_weights, score_resource
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


SOURCE_BROWSE_URLS = {
    "https://polyhaven.com/": "https://polyhaven.com/models",
    "https://kenney.nl/": "https://kenney.nl/assets",
    "https://ambientcg.com/": "https://ambientcg.com/list",
}


def _browse_url(source: Source, terms: set[str], kind: str | None) -> str:
    if source.canonical_url == "https://polyhaven.com/":
        if kind in ("texture", "material") or terms & {"texture", "pbr", "material"}:
            return "https://polyhaven.com/textures"
        if kind == "environment" or terms & {"hdri", "skybox", "lighting"}:
            return "https://polyhaven.com/hdris"
    return SOURCE_BROWSE_URLS.get(source.canonical_url, source.canonical_url)


def _fts_candidates(terms: set[str]):
    """PostgreSQL GIN-backed FTS, augmented by tag-only matches.

    The GIN expression is installed by revision 0003. Tags remain relational so
    they can be searched even when absent from an asset's title or description.
    """
    english = literal_column("'english'::regconfig")
    blank = literal_column("''")
    document = func.to_tsvector(
        english,
        func.coalesce(Resource.title, blank) + literal_column("' '")
        + func.coalesce(Resource.description, blank),
    )
    # Each term is optional (OR), preserving partial recall for longer prompts.
    expression = " OR ".join(sorted(term.replace("-", " ") for term in terms))
    fts = document.op("@@")(func.websearch_to_tsquery(english, expression))
    # LIKE is a recall-only candidate path (tree -> trees, forest -> rainforest).
    # The final exact-normalized ranker discards false positive substrings.
    tag_candidates = or_(*(Tag.slug.ilike(f"%{term}%") for term in sorted(terms)))
    return or_(fts, Resource.tags.any(tag_candidates))


def search_resources(
    session: Session,
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
    include_pending: bool = False,
    limit: int = 10,
) -> list[dict]:
    """Search with strict filters and explainable, age-neutral lexical ranking.

    PostgreSQL uses indexed FTS to select candidates; SQLite scans approved rows.
    Both databases apply identical deterministic scoring and filters afterward.
    Unknown formats never satisfy a format request.
    """
    if not 1 <= limit <= 100:
        raise CatalogError("Limit must be between 1 and 100")
    if len(query) > 500:
        raise CatalogError("Search query must not exceed 500 characters")
    if dimension:
        dimension = require_choice(dimension, DIMENSIONS, "dimension")
    else:
        dimension = infer_dimension(query)
    if kind:
        kind = require_choice(kind, KINDS, "kind")
    if access:
        access = require_choice(access, ACCESS_TYPES, "access")
    if license_status:
        license_status = require_choice(license_status, LICENSE_STATUSES, "license status")
    tag = normalize_tag(tag) if tag else None
    style = normalize_tag(style) if style else None
    subject = normalize_tag(subject) if subject else None
    if format is not None:
        parsed_formats = parse_formats(format)
        if len(parsed_formats) != 1:
            raise CatalogError("Choose one format, e.g. glb, fbx or png")
        format = parsed_formats[0]
    terms = query_terms(query)
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
    if license_status:
        statement = statement.where(Resource.license_status == license_status)
    if license_id:
        statement = statement.where(func.lower(Resource.license_id) == license_id.casefold())
    if terms and session.bind is not None and session.bind.dialect.name == "postgresql":
        statement = statement.where(_fts_candidates(terms))

    candidates = []
    for resource in session.scalars(statement):
        tags = {item.slug for item in resource.tags}
        if any(value and value not in tags for value in (tag, style, subject)):
            continue
        if format and format not in resource.formats:
            continue
        candidates.append(resource)
    weights = rarity_weights(candidates, terms) if terms else {}
    scored = []
    for resource in candidates:
        score, reasons = score_resource(resource, terms, weights)
        if terms and score == 0:
            continue
        data = resource_dict(resource)
        data["score"] = score
        data["match_reasons"] = reasons
        scored.append(data)
    scored.sort(key=lambda item: (-item["score"], item["title"].casefold(), item["id"]))
    return scored[:limit]


def find_sources(
    session: Session,
    query: str,
    *,
    dimension: str | None = None,
    kind: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Route the user to relevant *source directories*, not invented asset URLs.

    A source may cover a dimension even when the requested topic is absent from
    our snapshot. The response clearly distinguishes this from an indexed match.
    """
    if not 1 <= limit <= 100:
        raise CatalogError("Limit must be between 1 and 100")
    if len(query) > 500:
        raise CatalogError("Search query must not exceed 500 characters")
    dimension = require_choice(dimension, DIMENSIONS, "dimension") if dimension else infer_dimension(query)
    kind = require_choice(kind, KINDS, "kind") if kind else None
    terms = query_terms(query)
    if kind is None:
        inferred_kinds = terms & KINDS
        if len(inferred_kinds) == 1:
            kind = next(iter(inferred_kinds))
    sources = session.scalars(
        select(Source).options(selectinload(Source.resources).selectinload(Resource.tags))
    )
    results = []
    for source in sources:
        approved = [r for r in source.resources if r.review_status == "approved"]
        if not approved:
            continue
        covered_dimensions = sorted({r.dimension for r in approved})
        covered_kinds = sorted({r.kind for r in approved})
        if dimension and dimension != "both" and not any(
            r.dimension in (dimension, "both") for r in approved
        ):
            continue
        matching = []
        for resource in approved:
            if dimension and dimension != "both" and resource.dimension not in (dimension, "both"):
                continue
            score, _ = score_resource(resource, terms)
            if (not kind or resource.kind == kind) and (not terms or score > 0):
                matching.append(score)
        match_count = len(matching)
        kind_covered = bool(kind and kind in covered_kinds)
        result = {
            "name": source.name,
            "url": source.canonical_url,
            "browse_url": _browse_url(source, terms, kind),
            "policy_url": source.policy_url,
            "attribution_notice": source.attribution_notice,
            "covered_dimensions": covered_dimensions,
            "covered_kinds": covered_kinds,
            "indexed_matches": match_count,
            "match_basis": (
                "indexed matches" if match_count else
                "kind and dimension coverage" if kind_covered else "dimension coverage only"
            ),
            "verification_notice": "Directory recommendation only. Individual asset availability, formats and licensing must be checked at the source.",
            "reason": (
                f"{match_count} approved indexed link(s) overlap the request; browse for more."
                if match_count else "This source has relevant dimension coverage; the requested topic is not confirmed in this index."
            ),
        }
        results.append((max(matching, default=0), int(kind_covered), result))
    results.sort(key=lambda pair: (-pair[0], -pair[2]["indexed_matches"], -pair[1], pair[2]["name"].casefold()))
    return [result for _, _, result in results[:limit]]

