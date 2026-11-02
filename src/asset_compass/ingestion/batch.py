"""Manual CSV/JSON ingest; never fetches or scrapes the URLs in input files."""

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_compass.catalog import add_resource, add_source, review_resource
from asset_compass.models import Resource
from asset_compass.taxonomy import (
    ACCESS_TYPES, DIMENSIONS, KINDS, LICENSE_STATUSES, REVIEW_METHODS, REVIEW_STATUSES,
    parse_formats, parse_tags, require_choice,
)
from asset_compass.urls import canonicalize_url

MAX_INPUT_BYTES = 3_000_000
MAX_RECORDS = 5000


def load_records(path: Path) -> list[dict]:
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Input file missing or exceeds 3 MB")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
    elif path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    else:
        raise ValueError("Use a .json or .csv file")
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Expected an array of at most 5000 resource objects")
    return rows


def _as_csv(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value or "")


def _prepare_row(row: dict) -> dict:
    for field in ("source_url", "source_name", "url", "title", "dimension", "kind"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"Missing {field}")
    # Validate before touching the database; results are still revalidated by the catalog.
    canonicalize_url(row["url"])
    canonicalize_url(row["source_url"])
    parse_tags(_as_csv(row.get("tags")))
    parse_formats(_as_csv(row.get("formats")))
    require_choice(row["dimension"], DIMENSIONS, "dimension")
    require_choice(row["kind"], KINDS, "kind")
    require_choice(str(row.get("access") or "unknown"), ACCESS_TYPES, "access")
    license_status = require_choice(str(row.get("license_status") or "unknown"), LICENSE_STATUSES, "license status")
    if row.get("record_type") not in (None, "asset", "collection"):
        raise ValueError("Record type must be asset or collection")
    if license_status == "verified" and not (row.get("license_id") and row.get("license_url")):
        raise ValueError("Verified licenses require a license identifier and evidence URL")
    if row.get("license_url"):
        canonicalize_url(str(row["license_url"]))
    if row.get("source_policy_url"):
        canonicalize_url(str(row["source_policy_url"]))
    if row.get("review_status") is not None:
        require_choice(str(row["review_status"]), REVIEW_STATUSES, "review status")
        method = require_choice(str(row.get("review_method") or "none"), REVIEW_METHODS, "review method")
        if row.get("review_status") == "approved" and method == "none":
            raise ValueError("Approved records must declare a review method")
    return row


def import_records(session: Session, rows: Iterable[dict], *, dry_run: bool = False) -> dict:
    """Import valid rows using savepoints, retaining errors without partial rows."""
    report: dict[str, Any] = {"created": 0, "existing": 0, "valid_new": 0, "errors": []}
    seen_urls: set[str] = set()
    for index, row in enumerate(rows, start=1):
        try:
            row = _prepare_row(row)
            current_url = canonicalize_url(row["url"])
            if current_url in seen_urls:
                report["existing"] += 1
                continue
            seen_urls.add(current_url)
            existing = session.scalar(select(Resource.id).where(Resource.canonical_url == current_url))
            if existing:
                report["existing"] += 1
                continue
            if dry_run:
                report["valid_new"] += 1
                continue
            with session.begin_nested():
                source, _ = add_source(
                    session, row["source_url"], row["source_name"],
                    description=str(row.get("source_description") or ""),
                    policy_url=str(row.get("source_policy_url") or "") or None,
                    ingestion_method="official_api" if row.get("metadata_source") == "official_api" else "import",
                    attribution_notice="Powered by Poly Haven" if row.get("source_name") == "Poly Haven" else "",
                )
                resource, created = add_resource(
                    session, source_id=source.id, url=row["url"],
                    title=row["title"], dimension=row["dimension"], kind=row["kind"],
                    description=str(row.get("description") or ""),
                    tags=_as_csv(row.get("tags")), formats=_as_csv(row.get("formats")),
                    access=str(row.get("access") or "unknown"),
                    license_id=str(row.get("license_id") or "") or None,
                    license_url=str(row.get("license_url") or "") or None,
                    license_status=str(row.get("license_status") or "unknown"),
                    record_type=str(row.get("record_type") or "asset"),
                    author_name=str(row.get("author_name") or ""),
                    source_asset_id=str(row.get("source_asset_id") or "") or None,
                    source_tags=row.get("source_tags") if isinstance(row.get("source_tags"), list) else [],
                    metadata_source=str(row.get("metadata_source") or "batch_import"),
                )
                if created and row.get("review_status") in {"pending", "approved", "rejected"}:
                    review_resource(
                        session, resource.id, status=str(row["review_status"]),
                        method=str(row.get("review_method") or "none"),
                        note=str(row.get("review_note") or ""),
                    )
                report["created"] += int(created)
        except (ValueError, TypeError) as exc:
            report["errors"].append({"row": index, "url": str(row.get("url", ""))[:150], "error": str(exc)})
    return report


def export_records(session: Session, *, source_name: str | None = None) -> dict:
    """Export a minimal, importable link catalog; never mirrors original asset files."""
    records = []
    for resource in session.scalars(select(Resource).order_by(Resource.id)):
        source = resource.source
        if source_name and source.name.casefold() != source_name.casefold():
            continue
        records.append({
            "source_name": source.name,
            "source_url": source.canonical_url,
            "source_policy_url": source.policy_url,
            "url": resource.canonical_url,
            "title": resource.title,
            "description": "",  # Avoid copying third-party descriptions into version control.
            "dimension": resource.dimension,
            "kind": resource.kind,
            "record_type": resource.record_type,
            "tags": sorted(tag.slug for tag in resource.tags),
            "formats": resource.formats,
            "access": resource.access_type,
            "license_id": resource.license_id,
            "license_url": resource.license_url,
            "license_status": resource.license_status,
            "author_name": resource.author_name,
            "source_asset_id": resource.source_asset_id,
            "metadata_source": resource.metadata_source,
            "review_status": resource.review_status,
            "review_method": resource.review_method,
            "review_note": resource.review_note,
        })
    return {"records": records}

