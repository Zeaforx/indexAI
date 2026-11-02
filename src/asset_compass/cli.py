"""Curator commands. No third-party pages are fetched in Session 1."""

import json

import typer
from sqlalchemy.exc import OperationalError

from .catalog import (
    CatalogError, add_resource, add_source, annotate_resource, get_resource,
    list_sources, review_resource, search_resources,
)
from .db import initialize, make_engine, open_session
from .models import resource_dict
from .seed import seed_demo

app = typer.Typer(no_args_is_help=True, help="Curate and search 2D/3D asset links")
source_app = typer.Typer(no_args_is_help=True, help="Manage source destinations")
resource_app = typer.Typer(no_args_is_help=True, help="Manage asset and collection URLs")
app.add_typer(source_app, name="source")
app.add_typer(resource_app, name="resource")


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


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Words describing the asset"),
    dimension: str | None = typer.Option(None, "--dimension"),
    kind: str | None = typer.Option(None, "--kind"),
    tag: str | None = typer.Option(None, "--tag"),
    access: str | None = typer.Option(None, "--access"),
    include_pending: bool = typer.Option(False, "--include-pending"),
    limit: int = typer.Option(10, "--limit"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    try:
        with open_session(make_engine()) as session:
            items = search_resources(
                session, query, dimension=dimension, kind=kind, tag=tag,
                access=access, include_pending=include_pending, limit=limit,
            )
        if as_json:
            _output(items, as_json=True)
        else:
            if not items:
                _output("No matching approved resources. Try --include-pending for curator records.")
            for item in items:
                typer.echo(f"#{item['id']} [{item['dimension']}/{item['kind']}] {item['title']} (score {item['score']})")
                typer.echo(f"   {item['url']} | tags: {', '.join(item['tags'])}")
    except (ValueError, OperationalError) as exc:
        _fail(exc)


if __name__ == "__main__":
    app()

