# Asset Compass

An early, open-source catalog of useful **2D and 3D game-asset links** for AI-agent discovery. This is an index of destinations, collections and assets—not an asset file mirror or a general-purpose web crawler.

> **Status:** Session 6 local prototype. Reproducible seeds hold **110 real source-page links**: 27 Kenney 2D/3D packs, 53 Poly Haven models/textures and 30 ambientCG PBR materials. It includes explainable filtered search, read-only **REST + MCP** agent tools, cautious URL-health observations, verified SQLite backup/restore commands, local HTTP request throttling, and GitHub CI with a dedicated PostgreSQL service. **Public hosting, authentication, independent rights verification and live URL verification remain incomplete.**

## Setup

Requires Python 3.12+. From the `asset-compass` directory:

```bash
uv sync --extra dev
uv run assetindex init
uv run assetindex ingest file data/seed_kenney.json
uv run assetindex ingest file data/seed_polyhaven.json
uv run assetindex ingest file data/seed_kenney_expansion.json
uv run assetindex ingest file data/seed_ambientcg_materials.json
uv run assetindex ingest file data/seed_polyhaven_textures.json
uv run assetindex search "pixel platformer" --dimension 2d
uv run assetindex search "chair" --dimension 3d
uv run assetindex search "3d PBR wood floor texture" --license CC0-1.0 --license-status claimed
uv run assetindex search "3d flying dragon animation" --with-sources --json
uv run assetindex evaluate data/evaluation_queries_expanded.json
uv run assetindex evaluate data/evaluation_queries_holdout.json
uv run pytest
```

## REST API and AI-agent tools (Session 4)

After initializing and importing the catalog above, launch the read-only service:

```bash
uv run assetindex-api
```

It binds to **127.0.0.1:8000**, not a public interface. You can browse the interactive API documentation at <http://127.0.0.1:8000/docs> and try:

```bash
curl 'http://127.0.0.1:8000/healthz'
curl 'http://127.0.0.1:8000/v1/assets/search?q=3d%20binoculars&limit=3'
curl 'http://127.0.0.1:8000/v1/assets/search?q=3d%20flying%20dragon%20animation'
curl 'http://127.0.0.1:8000/v1/sources/search?q=2d%20zombie%20sprites'
curl 'http://127.0.0.1:8000/v1/assets/1'
```

These endpoints return structured JSON with canonical URLs, source attribution, formats (when known), license ID/evidence/status and relevance reasons. Pending or rejected resources are **never** exposed by the agent APIs. Query validation returns 422 for bad filters, missing resources return 404, and an unavailable database returns 503 without leaking connection details. OpenAPI is at `/openapi.json`.

The same server also exposes the official **MCP Streamable HTTP** protocol on <http://127.0.0.1:8000/mcp>. Tools: `search_assets`, `find_sources`, and `get_asset`. A local AI client can instead launch the MCP stdio server:

```bash
uv run assetindex-mcp
```

For a host supporting `mcpServers`, the equivalent configuration is:

```json
{
  "mcpServers": {
    "indexAI": {
      "command": "/absolute/path/to/asset-compass/.venv/bin/assetindex-mcp",
      "env": {"ASSET_COMPASS_DB_URL": "sqlite:////absolute/path/to/asset-compass/catalog.sqlite3"}
    }
  }
}
```

Use real **absolute paths** in a host configuration; a relative SQLite database URL depends on the working directory. Both protocols only read the database. Session 6 adds a simple **120 requests per 60 seconds per peer IP** sliding-window guard for REST and HTTP MCP; configure it with `ASSET_COMPASS_RATE_LIMIT` (1–1000). The guard ignores spoofable `X-Forwarded-For` headers and bounds its in-process state. It is **not** a distributed limit, user authentication, reverse-proxy configuration, request-body limiter, or TLS termination. **Keep this build on localhost; do not expose it directly to the internet.** See [Session 4 setup](docs/SESSION4.md) and [Session 6 security/recovery notes](docs/SESSION6.md).

Alternatively, use `python -m pip install -e '.[dev]'` and run `assetindex` directly. Local seed imports do **not** fetch webpages, so the 110-link catalog is reproducible offline. The original `data/evaluation_queries.json` is the earlier **45-link** benchmark; use the expanded evaluation file for the full Session 5 catalog.

To query the **live permitted Poly Haven API** instead of using the saved link snapshot:

```bash
uv run assetindex ingest polyhaven --limit 35 --dry-run
uv run assetindex ingest polyhaven --limit 35
uv run assetindex ingest polyhaven --type textures --limit 18 --dry-run
uv run assetindex ingest polyhaven --type hdris --limit 10 --dry-run
uv run assetindex ingest ambientcg --type material --limit 30 --dry-run
uv run assetindex ingest ambientcg --type hdri --limit 10 --dry-run
uv run assetindex ingest ambientcg --type 3d-model --limit 10 --dry-run
```

These adapters fetch bounded official metadata listings from Poly Haven or ambientCG with identifying User-Agent strings. Their snapshot sizes vary over time. In results, keep the source label **Poly Haven** visible as required by its API terms. No asset files or preview images are copied. Imported site-wide CC0 is recorded as **provider-claimed**. See [source policies](docs/SOURCE_POLICY.md).

### Cautious link-health checks (Session 5)

```bash
uv run assetindex check-links --limit 10
uv run assetindex check-links --source "Kenney" --limit 5
# Only when you deliberately want live network requests:
uv run assetindex check-links --source "Kenney" --limit 5 --execute
```

Without `--execute`, the command is a **read-only preview** and makes no network calls. Executing permits only sequential `HEAD` requests to explicitly allowlisted HTTPS hosts (`kenney.nl`, `polyhaven.com`, `ambientcg.com`), never follows redirects, uses small batches (maximum 20), pauses between calls, and skips links checked in the last 24 hours unless `--force --execute` is given. A response like 404 is marked `suspect_missing` rather than automatically removing a link or changing its review status. Some providers block `HEAD`; such results are **uncertain**, and this tool never performs a `GET` fallback. Live checking is not a licensing audit or proof that downloadable files work.

### Verified SQLite backup and recovery (Session 6)

```bash
# Use a new output path. First create the backups/ directory if needed.
uv run assetindex backup backups/catalog-2026-11-03.sqlite3
uv run assetindex verify-backup backups/catalog-2026-11-03.sqlite3
# Restore to a new path only; the active catalog stays unchanged.
uv run assetindex restore backups/catalog-2026-11-03.sqlite3 --to recovered.sqlite3
ASSET_COMPASS_DB_URL=sqlite:///./recovered.sqlite3 uv run assetindex search "pixel platformer"
```

Backups use SQLite's online backup API for a consistent snapshot, then check database integrity, foreign keys, catalog tables, schema version, counts and SHA-256. Snapshot files are atomically published only when the target path is free; **no command overwrites an existing database**. Keep copies off-device and test restoration regularly. These commands intentionally support **file-backed SQLite only**. For PostgreSQL, use `pg_dump`/`pg_restore` with managed credentials and test that restore on a disposable server.

By default, data is persisted in `./catalog.sqlite3` (ignored by git). The data model uses SQLAlchemy, initializes through versioned Alembic migrations, and accepts a PostgreSQL connection string through `ASSET_COMPASS_DB_URL`. An ephemeral PostgreSQL 16 CI test now exercises initialization and search, but a **production PostgreSQL deployment, backup and restore** remain separate milestones.

On PostgreSQL, migration `0003` installs an English-language GIN full-text index over titles and descriptions. Queries use `websearch_to_tsquery` to select candidates, including tag-only matches via the relational tag index. The final, explainable ranking is shared with SQLite. Session 6's [GitHub Actions run](https://github.com/Zeaforx/indexAI/actions/runs/41673311421) **passed** against an ephemeral PostgreSQL 16 service; this does not certify production performance or recovery.

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

Search supports `--dimension`, `--kind`, `--tag`, `--style`, `--subject`, `--format`, `--access`, `--license` and `--license-status`. Style and subject currently require exact normalized tags (e.g. `--style 'pixel art'` or `--subject forest`); they are **not** AI-inferred labels. The `--format` filter is strict: resources with unknown formats are excluded even when a provider commonly offers that format. A license filter does not turn a source's `claimed` rights into an independent verification.

Search uses a conservative synonym list (for example, `low poly`/`low-poly`, `pixel art`/`pixel-art`, `trees`/`tree`) and discounts generic query instructions. Matches are ranked by the locations of the terms (tags, titles, descriptions), with rare terms boosted. Results include `score` and `match_reasons`. No age-based penalty is applied; old links are intentionally eligible to rank highly. This is a deterministic lexical index, **not** an embedding or natural-language semantic search engine.

### Finding a source when no exact indexed asset exists

```bash
assetindex find-sources "3d flying dragon animation" --json
assetindex find-sources "2d zombie sprites" --json
assetindex search "3d flying dragon animation" --with-sources --json
assetindex search "2d pixel platformer" --format png --with-sources --json
```

`find-sources` returns trusted source browsing destinations, current catalog coverage, counts of overlapping indexed entries, and clear reasons. A source-level result does **not** claim the requested asset exists there. Search's default `--json` output remains a list of resource hits; use `--with-sources --json` for a `{ "resources": [...], "sources": [...] }` object, including when there are no hits. Plain-text search automatically prints browse suggestions when no resource matches. Neither search nor source routing fetches or scrapes webpages.

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
| `assetindex find-sources QUERY [filters]` | Recommend relevant source directories, including unindexed topics |
| `assetindex evaluate [FILE]` | Run reproducible relevance and fallback benchmark |
| `assetindex-api` | Start local read-only REST + Streamable HTTP MCP server |
| `assetindex-mcp` | Start read-only MCP tools over stdio for a local agent host |
| `assetindex seed-demo` | Add 10 synthetic demonstration records |
| `assetindex ingest polyhaven --type models\|textures\|hdris` | Save typed asset-page links via the official API |
| `assetindex ingest ambientcg --type material\|hdri\|3d-model` | Save typed material/HDRI/model links via the official API |
| `assetindex ingest file FILE [--dry-run]` | Validate and import curated JSON/CSV links |
| `assetindex resource list --status pending` | Inspect the curation queue |
| `assetindex export-file FILE [--source NAME]` | Export minimal, importable link metadata |
| `assetindex check-links [--limit 10] [--execute]` | Preview or opt into bounded HEAD-only health observations |
| `assetindex backup FILE.sqlite3` | Create a consistent, verified SQLite snapshot to a new file |
| `assetindex verify-backup FILE.sqlite3` | Verify SQLite structure, counts and SHA-256 |
| `assetindex restore FILE.sqlite3 --to NEW.sqlite3` | Restore a snapshot without replacing existing files |

`assetindex --help` and individual command `--help` pages list all options.

## Session 1 verification

Automated tests cover URL canonicalization, taxonomy normalization, foreign keys, persistence, deduplication, annotation, review states, format filters and search, plus CLI workflow tests. Test instructions and known limitations are tracked in [docs/SESSION1.md](docs/SESSION1.md).

## Session 2 verification

The [Session 2 report](docs/SESSION2.md) records live-API ingestion, the two sources, the offline restore, and current limitations. The importer preserves author/source metadata, distinguishes source-claimed CC0 from independently verified rights, and avoids inventing model file formats.

## Session 3 verification

The [Session 3 report](docs/SESSION3.md) documents indexed PostgreSQL FTS SQL, weighted ranking, exact-match filters and a 33-query evaluation using the 45 seed links. The benchmark assesses known queries and explicit no-hit routing, not unseen-domain quality. Tests run locally with SQLite and compile (but cannot execute) the PostgreSQL-specific SQL.

## Session 4 verification

The [Session 4 report](docs/SESSION4.md) describes the REST/MCP contracts, HTTP JSON-RPC integration tests, localhost security boundaries and remaining steps before a publicly reachable service. The MCP stdio entry point is configured and test-inspected; a full subprocess stdio round trip requires an environment with working asynchronous subprocess/pipe handling.

## Session 5 verification

The [Session 5 report](docs/SESSION5.md) records the 110-link snapshot composition, the official API usage and provider policy evidence, the conservative `HEAD`-only checker, the 32/32 in-sample expanded query benchmark, and the remaining production concerns. **These checks are local; individual links have not been exhaustively tested live.**

## Session 6 verification

The [Session 6 report](docs/SESSION6.md) describes tested SQLite backup/recovery, API and MCP request throttling, input bounds, a second **23/24** task-worded search evaluation, and two GitHub Actions jobs (SQLite/tests/package plus a live PostgreSQL service migration/full-text integration test). **Both CI jobs passed** in the [verified run](https://github.com/Zeaforx/indexAI/actions/runs/41673311421). The workflow also supports manual **Run workflow**. One evaluation miss is documented; this second set is not a blind real-user benchmark.

## Roadmap

1. **Complete:** Foundation with local catalog, tags, sources/resources, curator CLI and tests.
2. **Complete:** Poly Haven official API ingestion, Kenney curated seed, provenance fields and 45 real links.
3. **Complete locally:** PostgreSQL full-text index migration, relevance ranking, source fallback, strict filters and evaluation.
4. **Complete locally:** Read-only REST API, MCP Streamable HTTP and stdio tools, source/rights attribution, validation and integration tests.
5. **Complete locally:** Catalog expansion to 110 links, ambientCG and Poly Haven texture ingestion, Kenney UI/sprites/animations, safe previewable URL-health checker and expanded search evaluation.
6. **Complete, CI green:** Recovery-safe SQLite backups, HTTP request throttling, task-worded search evaluation, CI SQLite/build verification and live PostgreSQL integration.
7. **Next:** Add authentication and public deployment protections, provision hosting and monitor a deployed service when infrastructure is chosen.

Code is MIT licensed. Third-party links, metadata and asset files remain subject to their owners' terms; the code license does not grant rights to them.

