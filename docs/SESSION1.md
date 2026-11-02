# Session 1 — Foundation

## Implemented

- Python package, CLI and reproducible dependency specification.
- Versioned initial Alembic migration for database tables: sources, resources, tags, resource_tags. Foreign keys and unique canonical URLs.
- SQLite local persistence and PostgreSQL-compatible SQLAlchemy model and connection configuration.
- Source entry, resource entry, metadata annotation, review status, structured show, filtered keyword search.
- Controlled 2D/3D categories and tag aliasing.
- Ten synthetic demonstration resources, clearly labeled as fictional.
- Automated unit/integration/CLI tests.

## Verification checklist

Run:

```bash
uv sync --extra dev
uv run pytest -q
uv run assetindex init
uv run assetindex seed-demo
uv run assetindex search "low poly forest" --dimension 3d --json
```

Expected behavior: the search returns the fictional `Low Poly Forest Trees` record, including `low-poly` and `forest` tags; repeating the seed step adds zero resources.

### Verification recorded 2 November 2026

- `pytest -q`: **15 passed**.
- `uv build --offline`: source distribution and wheel built successfully.
- Fresh, isolated wheel install: `assetindex init`, `seed-demo`, and `search 'low poly forest' --dimension 3d` succeeded.
- Live PostgreSQL connection: **not tested** because no local PostgreSQL server was available.

## Honest limitations

- No third-party source discovery or link fetching yet.
- The demo catalog is synthetic; it must not be presented as real assets.
- Ranking is deliberately lexical and in-process. Session 3 will add indexed PostgreSQL full-text search and better source matching.
- While the model supports a PostgreSQL URL, no live PostgreSQL instance is available in this workspace to validate it yet.
- `init` upgrades the database through the bundled Alembic migration. These migrations have been tested locally on SQLite; PostgreSQL needs a separate live integration test.
- No external API, MCP server, authentication layer or public service exists yet.

