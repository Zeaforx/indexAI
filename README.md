# Asset Compass

An early, open-source catalog of useful **2D and 3D game-asset links** for AI-agent discovery. This is an index of destinations, collections and assets—not an asset file mirror or a general-purpose web crawler.

> **Status:** Session 2 local prototype. The catalog includes reproducible seeds for **45 real link records** (35 Poly Haven 3D models and 10 Kenney 2D packs) and an official Poly Haven API adapter. Search is still basic. A hosted PostgreSQL deployment, REST and MCP are planned for later sessions.

## Setup

Requires Python 3.12+. From the `asset-compass` directory:

```bash
uv sync --extra dev
uv run assetindex init
uv run assetindex ingest file data/seed_kenney.json
uv run assetindex ingest file data/seed_polyhaven.json
uv run assetindex search "pixel platformer" --dimension 2d
uv run assetindex search "chair" --dimension 3d
uv run pytest
```

Alternatively, use `python -m pip install -e '.[dev]'` and run `assetindex` directly. Local seed imports do **not** fetch webpages, so the 45-link example catalog is reproducible offline.

To query the **live permitted Poly Haven API** instead of using the saved link snapshot:

```bash
uv run assetindex ingest polyhaven --limit 35 --dry-run
uv run assetindex ingest polyhaven --limit 35
```

The adapter makes a single bounded request to `api.polyhaven.com` with an identifying User-Agent. In results, keep the source label **Poly Haven** visible as required by its API terms. No asset files or preview images are copied. See [source policies](docs/SOURCE_POLICY.md).

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

### Importing and exporting curated links

The `ingest file` command accepts a JSON object containing `records` or a CSV with the same field names. Required fields are `source_url`, `source_name`, `url`, `title`, `dimension`, and `kind`. New manually supplied records default to **pending** unless a review status and valid review method are explicitly provided. Invalid rows are reported; valid rows are committed independently, with no half-written records.

```bash
uv run assetindex ingest file data/seed_kenney.json --dry-run
uv run assetindex ingest file data/seed_kenney.json
uv run assetindex resource list --status pending
uv run assetindex export-file my-links.json
```

Use `--overwrite` only when you intend to replace an existing export. Reimporting the same file is idempotent. Exports intentionally omit external asset descriptions to keep the committed catalog focused on links and annotations. The included seed files remain subject to source metadata terms and are not licensed as third-party asset files by our code license.

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
| `assetindex ingest polyhaven --limit 35` | Discover and save real 3D model links from the official API |
| `assetindex ingest file FILE [--dry-run]` | Validate and import curated JSON/CSV links |
| `assetindex resource list --status pending` | Inspect the curation queue |
| `assetindex export-file FILE [--source NAME]` | Export minimal, importable link metadata |

`assetindex --help` and individual command `--help` pages list all options.

## Session 1 verification

Automated tests cover URL canonicalization, taxonomy normalization, foreign keys, persistence, deduplication, annotation, review states, format filters and search, plus CLI workflow tests. Test instructions and known limitations are tracked in [docs/SESSION1.md](docs/SESSION1.md).

## Session 2 verification

The [Session 2 report](docs/SESSION2.md) records live-API ingestion, the two sources, the offline restore, and current limitations. The importer preserves author/source metadata, distinguishes source-claimed CC0 from independently verified rights, and avoids inventing model file formats.

## Roadmap

1. **Complete:** Foundation with local catalog, tags, sources/resources, curator CLI and tests.
2. **Complete:** Poly Haven official API ingestion, Kenney curated seed, provenance fields and 45 real links.
3. **Next:** Full-text relevance ranking, curated source fallback and filters.
4. REST API and read-only MCP agent tools.
5. Catalog expansion and link health checks (basic exports already available).
6. Security, benchmark tests, backups and recovery.
7. Live deployment, monitoring and documentation.

Code is MIT licensed. Third-party links, metadata and asset files remain subject to their owners' terms; the code license does not grant rights to them.

