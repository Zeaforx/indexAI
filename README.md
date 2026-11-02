# Asset Compass

An early, open-source catalog of useful **2D and 3D game-asset links** for AI-agent discovery. This is an index of destinations, collections and assets—not an asset file mirror or a general-purpose web crawler.

> **Status:** Session 1 local prototype. Search is intentionally basic, and the demo seed data is fictional. External source discovery, live-source imports, a PostgreSQL deployment, REST and MCP are planned for later sessions.

## Setup

Requires Python 3.12+. From the `asset-compass` directory:

```bash
uv sync --extra dev
uv run assetindex init
uv run assetindex seed-demo
uv run assetindex search "low poly forest" --dimension 3d
uv run pytest
```

Alternatively, use `python -m pip install -e '.[dev]'` and run `assetindex` directly. No web requests are made by the Session 1 CLI.

By default, data is persisted in `./catalog.sqlite3` (ignored by git). The data model uses SQLAlchemy, initializes through a versioned Alembic migration, and accepts a PostgreSQL connection string through `ASSET_COMPASS_DB_URL`; a PostgreSQL deployment and restore test will be verified separately. Do not assume the local SQLite tests certify a PostgreSQL server.

For PostgreSQL, configure something like:

```bash
export ASSET_COMPASS_DB_URL='postgresql+psycopg://user:password@localhost:5432/assetcompass'
assetindex init
```

Keep credentials in environment variables; do not commit them.

## Using real links

```bash
assetindex init
assetindex source add https://example.org --name "Example Source"
assetindex source list
assetindex resource add https://example.org/forest-kit \
  --source 1 --title "Forest Kit" --dimension 3d --kind environment \
  --tags "forest,low poly,trees" --formats "gltf,blend" \
  --access unknown
assetindex resource annotate 1 --tags "3d,low-poly,forest,tree"
assetindex resource review 1 --status approved --method ai-assisted \
  --note "Example only; review origin and rights before using real entries"
assetindex search "low poly forest" --dimension 3d
assetindex resource show 1
```

Replace all example URLs with actual source/asset pages. The resource commands do not download asset files or automatically verify licenses. Newly added resources begin in `pending` status; normal search only returns approved resources. Use `--include-pending` for curatorial inspection.

### Metadata and licensing

The database separately tracks `access_type` (`free`, `paid`, `mixed`, `unknown`) and `license_status` (`unknown`, `claimed`, `verified`). A record cannot be marked `verified` without both a license identifier and evidence URL. This validates *presence of evidence fields*, not the legal meaning of a license: actual source policies and asset pages must be checked.

Review methods distinguish `automated`, `ai-assisted` and `human`. Do not call an AI-assisted review human-reviewed. Source and resource URLs are normalized for identity, and duplicate URLs are not inserted again.

The built-in demo uses `example.org` placeholder URLs and **does not link to downloadable assets**. Use `seed-demo` only to test program behavior.

## Commands

| Command | Purpose |
| --- | --- |
| `assetindex init` | Create relational schema, safely repeatable |
| `assetindex source add URL --name NAME` | Store a specialist destination |
| `assetindex source list` | Show source IDs and URLs |
| `assetindex resource add URL --source ID ...` | Store an asset/collection candidate |
| `assetindex resource annotate ID --tags ...` | Change descriptions, tags, formats or license metadata |
| `assetindex resource review ID --status ... --method ...` | Record approval/rejection and review method |
| `assetindex resource show ID` | Show structured metadata |
| `assetindex search QUERY [filters]` | Rank approved stored resources |
| `assetindex seed-demo` | Add 10 synthetic demonstration records |

`assetindex --help` and individual command `--help` pages list all options.

## Session 1 verification

Automated tests cover URL canonicalization, taxonomy normalization, foreign keys, persistence, deduplication, annotation, review states, format filters and search, plus CLI workflow tests. Test instructions and known limitations are tracked in [docs/SESSION1.md](docs/SESSION1.md).

## Roadmap

1. **Complete:** Foundation with local catalog, tags, sources/resources, curator CLI and tests.
2. Next: Approved external-source discovery/import, real evidence checks and initial 30–50 entries.
3. Full-text relevance ranking, curated source fallback and filters.
4. REST API and read-only MCP agent tools.
5. Catalog expansion, link health checks and export.
6. Security, benchmark tests, backups and recovery.
7. Live deployment, monitoring and documentation.

Code is MIT licensed. Third-party links, metadata and asset files remain subject to their owners' terms; the code license does not grant rights to them.

