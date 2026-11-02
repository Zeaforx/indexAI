"""Curator and discovery commands. Search runs against locally stored metadata."""

import json
from pathlib import Path

import typer
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from .catalog import (
    CatalogError, add_resource, add_source, annotate_resource, get_resource,
    find_sources, list_sources, review_resource, search_resources,
)
from .db import initialize, make_engine, open_session
from .evaluation import run_evaluation
from .ingestion.batch import export_records, import_records, load_records
from .ingestion.ambientcg import AmbientCGError, fetch_listing as fetch_ambient_listing, select_assets as select_ambient_assets
from .ingestion.polyhaven import IngestionError, fetch_listing as fetch_poly_listing, select_assets as select_poly_assets
from .link_health import check_links
from .models import Resource, resource_dict
from .seed import seed_demo

app = typer.Typer(no_args_is_help=True, help="Curate and search 2D/3D asset links")
source_app = typer.Typer(no_args_is_help=True, help="Manage source destinations")
resource_app = typer.Typer(no_args_is_help=True, help="Manage asset and collection URLs")
app.add_typer(source_app, name="source")
app.add_typer(resource_app, name="resource")
ingest_app = typer.Typer(no_args_is_help=True, help="Import catalog entries from reviewed sources")
app.add_typer(ingest_app, name="ingest")


def _fail(exc: Exception) -> None:
    if isinstance(exc, OperationalError):
        typer.secho("Database not initialized or unavailable. Run: assetindex init", fg=typer.colors.RED, err=True)
    else:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _output(value, *, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps(value, indent=2, ensure_ascii=False))
    elif isinstance(value, str):
        typer.echo(value)
    else:
        typer.echo(json.dumps(value, indent=2, ensure_ascii=False))


@app.command("init")
def init_db() -> None:
    """Create the catalog tables if missing (safe to rerun)."""
    try:
        engine = make_engine()
        initialize(engine)
        _output("Database ready.")
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@app.command("seed-demo")
def seed_demo_cmd() -> None:
    """Insert ten SYNTHETIC examples. Their URLs are not real assets."""
    try:
        with open_session(make_engine()) as session:
            count = seed_demo(session)
        _output(f"Added {count} fictional demo resources. These are not downloadable assets.")
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@source_app.command("add")
def source_add(
    url: str = typer.Argument(..., help="Source homepage URL"),
    name: str = typer.Option(..., "--name", help="Source name"),
    description: str = typer.Option("", "--description"),
    policy_url: str | None = typer.Option(None, "--policy-url"),
) -> None:
    try:
        with open_session(make_engine()) as session:
            source, created = add_source(session, url, name, description, policy_url)
            result = f"{'Created' if created else 'Already exists'} source #{source.id}: {source.name} ({source.canonical_url})"
        _output(result)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@source_app.command("list")
def source_list(as_json: bool = typer.Option(False, "--json")) -> None:
    try:
        with open_session(make_engine()) as session:
            items = [{"id": item.id, "name": item.name, "url": item.canonical_url} for item in list_sources(session)]
        _output(items, as_json=as_json)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@resource_app.command("add")
def resource_add(
    url: str = typer.Argument(...),
    title: str = typer.Option(..., "--title"),
    source: int = typer.Option(..., "--source", help="Source ID from 'source list'"),
    dimension: str = typer.Option(..., "--dimension", help="2d, 3d or both"),
    kind: str = typer.Option(..., "--kind", help="e.g. model, tileset, environment"),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    formats: str = typer.Option("", "--formats", help="Comma-separated formats"),
    description: str = typer.Option("", "--description"),
    access: str = typer.Option("unknown", "--access"),
    license_id: str | None = typer.Option(None, "--license"),
    license_url: str | None = typer.Option(None, "--license-url"),
    license_status: str = typer.Option("unknown", "--license-status"),
    record_type: str = typer.Option("asset", "--type"),
) -> None:
    try:
        with open_session(make_engine()) as session:
            resource, created = add_resource(
                session, url=url, source_id=source, title=title, dimension=dimension,
                kind=kind, tags=tags, formats=formats, description=description,
                access=access, license_id=license_id, license_url=license_url,
                license_status=license_status, record_type=record_type,
            )
            result = f"{'Created' if created else 'Already exists'} resource #{resource.id}: {resource.title} (pending review)"
        _output(result)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@resource_app.command("annotate")
def resource_annotate(
    resource_id: int = typer.Argument(...),
    tags: str | None = typer.Option(None, "--tags", help="Replace tag list; comma-separated"),
    formats: str | None = typer.Option(None, "--formats"),
    description: str | None = typer.Option(None, "--description"),
    access: str | None = typer.Option(None, "--access"),
    license_id: str | None = typer.Option(None, "--license"),
    license_url: str | None = typer.Option(None, "--license-url"),
    license_status: str | None = typer.Option(None, "--license-status"),
) -> None:
    try:
        with open_session(make_engine()) as session:
            resource = annotate_resource(
                session, resource_id, tags=tags, formats=formats,
                description=description, access=access, license_id=license_id,
                license_url=license_url, license_status=license_status,
            )
            data = resource_dict(resource)
        _output(data)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@resource_app.command("review")
def resource_review(
    resource_id: int = typer.Argument(...),
    status: str = typer.Option(..., "--status", help="pending, approved, rejected"),
    method: str = typer.Option(..., "--method", help="automated, ai-assisted or human"),
    note: str = typer.Option("", "--note"),
) -> None:
    try:
        with open_session(make_engine()) as session:
            resource = review_resource(session, resource_id, status=status, method=method, note=note)
            result = f"Resource #{resource.id}: {resource.review_status} ({resource.review_method})"
        _output(result)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@resource_app.command("show")
def resource_show(resource_id: int) -> None:
    try:
        with open_session(make_engine()) as session:
            data = resource_dict(get_resource(session, resource_id))
        _output(data, as_json=True)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@resource_app.command("list")
def resource_list(
    status: str = typer.Option("pending", "--status", help="pending, approved, rejected, or all"),
    limit: int = typer.Option(30, "--limit"),
) -> None:
    if status not in {"pending", "approved", "rejected", "all"} or not 1 <= limit <= 200:
        _fail(ValueError("Status must be pending/approved/rejected/all and limit 1–200"))
    try:
        with open_session(make_engine()) as session:
            statement = select(Resource).order_by(Resource.id).limit(limit)
            if status != "all":
                statement = statement.where(Resource.review_status == status)
            items = [{"id": x.id, "title": x.title, "status": x.review_status, "url": x.canonical_url} for x in session.scalars(statement)]
        _output(items, as_json=True)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@ingest_app.command("file")
def ingest_file(
    path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without saving records"),
) -> None:
    """Import reviewed link metadata from CSV/JSON. Never fetches submitted URLs."""
    try:
        rows = load_records(path)
        with open_session(make_engine()) as session:
            report = import_records(session, rows, dry_run=dry_run)
        report["dry_run"] = dry_run
        _output(report, as_json=True)
        if report["errors"]:
            raise typer.Exit(code=1)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@ingest_app.command("polyhaven")
def ingest_polyhaven(
    limit: int = typer.Option(35, "--limit", help="Maximum asset pages (1–200)"),
    asset_type: str = typer.Option("models", "--type", help="models, textures or hdris"),
    query: str = typer.Option("", "--query", help="Optional topic filter"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without saving"),
) -> None:
    """Fetch one official Poly Haven models/textures/HDRIs listing with source credit."""
    try:
        rows = [candidate.as_import_record() for candidate in select_poly_assets(
            fetch_poly_listing(asset_type=asset_type), asset_type=asset_type, limit=limit, query=query,
        )]
        with open_session(make_engine()) as session:
            report = import_records(session, rows, dry_run=dry_run)
        report.update({"source": "Poly Haven", "type": asset_type, "candidates": len(rows), "dry_run": dry_run})
        _output(report, as_json=True)
        if report["errors"]:
            raise typer.Exit(code=1)
    except (ValueError, OperationalError, IngestionError) as exc:
        _fail(exc)


@ingest_app.command("ambientcg")
def ingest_ambientcg(
    limit: int = typer.Option(30, "--limit", help="Maximum selected links (1–80)"),
    asset_type: str = typer.Option("material", "--type", help="material, hdri or 3d-model"),
    query: str = typer.Option("", "--query", help="Optional provider search, 100 characters max"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without saving"),
) -> None:
    """Fetch one bounded official ambientCG API page; only record asset URLs."""
    try:
        payload = fetch_ambient_listing(asset_type=asset_type, limit=80, query=query)
        rows = [candidate.as_import_record() for candidate in select_ambient_assets(
            payload, asset_type=asset_type, limit=limit,
        )]
        with open_session(make_engine()) as session:
            report = import_records(session, rows, dry_run=dry_run)
        report.update({"source": "ambientCG", "type": asset_type, "candidates": len(rows), "dry_run": dry_run})
        _output(report, as_json=True)
        if report["errors"]:
            raise typer.Exit(code=1)
    except (ValueError, OperationalError, AmbientCGError) as exc:
        _fail(exc)


@app.command("export-file")
def export_file(
    path: Path = typer.Argument(..., help="Destination .json file"),
    source_name: str | None = typer.Option(None, "--source", help="Only export one named source"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Explicitly replace an existing export"),
) -> None:
    """Export link metadata for backup, curation and reproducible imports."""
    if path.suffix.lower() != ".json":
        _fail(ValueError("Export path must end with .json"))
    if path.exists() and not overwrite:
        _fail(ValueError(f"File exists: {path}. Use --overwrite to replace it"))
    if not path.parent.exists():
        _fail(ValueError(f"Parent directory does not exist: {path.parent}"))
    try:
        with open_session(make_engine()) as session:
            payload = export_records(session, source_name=source_name)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _output(f"Exported {len(payload['records'])} link records to {path}")
    except (ValueError, OperationalError, OSError) as exc:
        _fail(exc)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Words describing the asset"),
    dimension: str | None = typer.Option(None, "--dimension"),
    kind: str | None = typer.Option(None, "--kind"),
    tag: str | None = typer.Option(None, "--tag"),
    style: str | None = typer.Option(None, "--style", help="Exact style tag, e.g. pixel-art"),
    subject: str | None = typer.Option(None, "--subject", help="Exact subject tag, e.g. forest"),
    format: str | None = typer.Option(None, "--format", help="Known download format (strict match)"),
    access: str | None = typer.Option(None, "--access"),
    license_id: str | None = typer.Option(None, "--license", help="License identifier, e.g. CC0-1.0"),
    license_status: str | None = typer.Option(None, "--license-status", help="unknown, claimed, verified"),
    include_pending: bool = typer.Option(False, "--include-pending"),
    limit: int = typer.Option(10, "--limit"),
    as_json: bool = typer.Option(False, "--json"),
    with_sources: bool = typer.Option(False, "--with-sources", help="Return source recommendations alongside resource hits (JSON object)"),
) -> None:
    try:
        with open_session(make_engine()) as session:
            items = search_resources(
                session, query, dimension=dimension, kind=kind, tag=tag,
                style=style, subject=subject, format=format, access=access,
                license_id=license_id, license_status=license_status,
                include_pending=include_pending, limit=limit,
            )
            sources = find_sources(session, query, dimension=dimension, kind=kind) if not items or with_sources else []
        if as_json:
            _output({"resources": items, "sources": sources} if with_sources else items, as_json=True)
        else:
            if not items:
                _output("No exact approved indexed resource. Broader source directories to explore:")
                if not sources:
                    _output("No matching catalog sources; try adding a curated source.")
                for source in sources:
                    typer.echo(f"   {source['name']} — {source['browse_url']} ({source['match_basis']})")
            for item in items:
                typer.echo(f"#{item['id']} [{item['dimension']}/{item['kind']}] {item['title']} (score {item['score']})")
                typer.echo(f"   {item['url']} | tags: {', '.join(item['tags'])}")
                typer.echo(f"   Matched: {', '.join(item['match_reasons'])}")
            if items and with_sources:
                typer.echo("Browse related sources:")
                for source in sources:
                    typer.echo(f"   {source['name']} — {source['browse_url']}")
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@app.command("find-sources")
def find_sources_cmd(
    query: str = typer.Argument(..., help="What type of 2D/3D assets are you seeking?"),
    dimension: str | None = typer.Option(None, "--dimension"),
    kind: str | None = typer.Option(None, "--kind"),
    limit: int = typer.Option(5, "--limit"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Recommend indexed source directories even when no exact link exists."""
    try:
        with open_session(make_engine()) as session:
            sources = find_sources(session, query, dimension=dimension, kind=kind, limit=limit)
        if as_json:
            _output(sources, as_json=True)
        elif not sources:
            _output("No matching source directory indexed yet.")
        else:
            for source in sources:
                typer.echo(f"{source['name']}: {source['browse_url']}")
                typer.echo(f"   {source['reason']}")
    except (ValueError, OperationalError) as exc:
        _fail(exc)


@app.command("evaluate")
def evaluate(
    path: Path = typer.Argument(Path("data/evaluation_queries.json"), help="JSON benchmark with a cases array"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Measure top-five indexed asset hits and no-hit source routing."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases = payload.get("cases") if isinstance(payload, dict) else None
        if not isinstance(cases, list):
            raise ValueError("Evaluation file must contain a cases array")
        with open_session(make_engine()) as session:
            report = run_evaluation(session, cases)
        if as_json:
            _output(report, as_json=True)
        else:
            typer.echo(f"Search benchmark: {report['passed']}/{report['cases']} scenarios passed")
            typer.echo(f"Asset hit@5: {report['asset_hit_at_5']:.1%}; source fallback: {report['source_fallback_rate']:.1%}")
            for case in report["details"]:
                if not case["passed"]:
                    typer.echo(f"   MISS: {case['query']} (expected {case['expected']}; got {case['top_results']})")
        if report["passed"] != report["cases"]:
            raise typer.Exit(code=1)
    except (ValueError, OperationalError, OSError, json.JSONDecodeError) as exc:
        _fail(exc)


@app.command("check-links")
def check_links_cmd(
    limit: int = typer.Option(10, "--limit", help="1–20 approved links per batch"),
    source_name: str | None = typer.Option(None, "--source", help="Only this saved publisher name"),
    execute: bool = typer.Option(False, "--execute", help="Opt in to live HEAD requests and save observations"),
    force: bool = typer.Option(False, "--force", help="Recheck inside the 24-hour cooldown (requires --execute)"),
) -> None:
    """Preview link health; explicitly execute gentle, redirect-free HEAD checks."""
    if force and not execute:
        _fail(ValueError("--force requires --execute"))
    try:
        with open_session(make_engine()) as session:
            report = check_links(session, limit=limit, source_name=source_name, execute=execute, force=force)
        _output(report, as_json=True)
    except (ValueError, OperationalError) as exc:
        _fail(exc)


if __name__ == "__main__":
    app()

