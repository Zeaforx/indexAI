# Build Session 6 — recoverability, request throttling and CI

Built locally: **3 November 2026**. Session 6 keeps the **110-link** offline catalog and the read-only REST + MCP interface from Session 5. Its focus is preventing accidental data loss, bounding simple request floods, and obtaining independent database-engine test results.

## What was delivered

| Capability | What is implemented | Verified locally? |
| --- | --- | --- |
| SQLite backup | SQLite online backup API, read-only source, verified temporary snapshot, atomic new-file hard link | Yes |
| Backup inspection | `PRAGMA integrity_check`, `foreign_key_check`, required catalog tables, Alembic revision, counts, SHA-256 | Yes |
| SQLite restore | Accept only valid catalog snapshot; restore to a **new** file; never replace existing data | Yes |
| REST + MCP request throttling | Sliding-window guard per actual peer IP; default 120 requests/60 seconds, `429` and `Retry-After` on excess | Yes, with deterministic time-based tests |
| Bounded server inputs | REST/MCP string filters limited to 100 characters; normalized tags cannot exceed database column length | Yes |
| Additional relevance evaluation | Task-worded prompts separate from original benchmark; **23/24** match expected top-five/fallback | Yes |
| PostgreSQL integration test | Test real migration `0001`–`0004`, GIN index, full-text title lookup and tag-only candidates | In GitHub CI; **not runnable locally** |
| GitHub Actions | SQLite/unit/API/MCP/recovery tests + package build; separate PostgreSQL 16 service test | Workflow authored; verify the published Actions run |

### Backup / verification / restore

```bash
mkdir -p backups
uv run assetindex backup backups/catalog-s6.sqlite3
uv run assetindex verify-backup backups/catalog-s6.sqlite3
uv run assetindex restore backups/catalog-s6.sqlite3 --to recovered-s6.sqlite3
ASSET_COMPASS_DB_URL=sqlite:///./recovered-s6.sqlite3 uv run assetindex search '2d pixel platformer'
```

The backup and restore commands are **SQLite-only** and accept only file-backed SQLite database URLs or snapshot paths. A destination must end in `.sqlite3` or `.db`, must have an existing parent directory and **must not already exist**. This is deliberate: an accidental repeated command cannot silently overwrite a live catalog or prior backup. A temporary file is created beside the destination, populated through SQLite's transactionally consistent `Connection.backup()` API and verified. Only then is it atomically made visible under the destination name; temporary files are removed if an operation fails.

The verification command reports:

- Absolute path, database schema revision and catalog resource/source counts.
- SQLite integrity status, physical file size and SHA-256 digest.
- It rejects corrupt, non-catalog, foreign-key-inconsistent and missing snapshots.

**Operational practice:** back up before imports and migrations, rotate old backups explicitly, and retain encrypted or access-controlled copies outside the machine. SHA-256 is an integrity fingerprint, not authentication against malicious substitution. These commands do not run unattended or replace an external backup schedule. PostgreSQL needs its own `pg_dump`/`pg_restore` plan and a tested disposable restore target; the SQLite snapshot commands intentionally reject PostgreSQL URLs.

### Request throttling and security

The `RateLimitGuard` pure-ASGI middleware covers `/v1/...` REST endpoints and `/mcp` Streamable HTTP messages. It uses a sliding 60-second counter per **actual ASGI peer address** with default 120 requests, a maximum configurable rate of 1000, and a bounded active-client map. `/healthz` remains available as a readiness probe. The limiter is configured using:

```bash
ASSET_COMPASS_RATE_LIMIT=120 uv run assetindex-api
```

Excessive requests receive HTTP `429`, a `Retry-After` header, and no catalog result. `X-Forwarded-For` is **not trusted** because accepting it directly would allow easy spoofing. This is a single-process, in-memory safety guard: worker restarts reset counters, separate workers do not share state, a reverse proxy may make all clients appear to have the same address, and it does not provide account-level quotas or authorization. The MCP **stdio** transport has no HTTP client address and is not covered by this guard. The server still binds to `127.0.0.1`; **do not expose it publicly** without authentication, reverse-proxy rate controls, TLS, request-body limits and deployment review.

### Search-quality reality check

The original [Session 5 benchmark](../data/evaluation_queries_expanded.json) has **32/32** passing authored cases against the 110-record catalog. Session 6 adds 24 new task-phrased queries in `data/evaluation_queries_holdout.json`, tested against the same snapshot:

| Measure | Observed result |
| --- | ---: |
| Total task-worded scenarios | **23/24** pass |
| Expected asset found in top 5 | **17/18** = 94.4% |
| Correct directory fallback for deliberate no-hit queries | **6/6** = 100% |

The additional set initially passed only **20/24**, exposing simple lexical gaps for plural UI words and common shape/size expressions. A small, explainable synonym update improves this to **23/24**. One intentionally tracked miss remains: **“retro background art for a 2d side scroller”** does not find the expected older Kenney *Background Elements* pack within the top five. We will not invent a `retro` label for the pack to make a test pass. These hand-authored queries were examined during development, so the result is **not** a genuinely blind or representative evaluation of arbitrary users. Real user-provided prompts are a necessary future milestone.

### Local verification

Run from the repository directory:

```bash
uv sync --frozen --extra dev
uv run pytest -q
uv run assetindex evaluate data/evaluation_queries_expanded.json
uv run assetindex evaluate data/evaluation_queries_holdout.json
uv build
```

The holdout CLI deliberately exits nonzero while a failing case remains; this does **not** mean the unit-test suite is broken. The automated test asserts the recorded baseline is at least 23/24 and tracks fallback accuracy. The PostgreSQL integration test is skipped locally unless `ASSET_COMPASS_TEST_POSTGRES_URL` explicitly points to a **disposable PostgreSQL database**. It creates and populates schema/data on that server, so do not aim it at a production database.

### CI workflow

File: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). GitHub Actions is configured for pushes to `main`, pull requests, and manual **Run workflow** invocation from the Actions tab:

1. **SQLite, API, MCP, recovery, build** — install pinned dependencies from `uv.lock`, run the full local test suite and build both distribution artifacts.
2. **Live PostgreSQL 16** — start an ephemeral PostgreSQL service, initialize all Alembic migrations and test GIN full-text/title search plus relational tag matches.

Until the first CI run completes, report this as **configured**, not as a previously passing live PostgreSQL environment. GitHub API publication of a workflow may not itself trigger Actions; if no run appears, use **Run workflow** from the repository's Actions tab (and enable Actions if the repository currently has them disabled). Actions depend on available runners, official action versions and network availability.

## Still outstanding

1. Public deployment authentication, TLS and reverse-proxy protections. The current service is deliberately localhost-only.
2. Distributed quotas, robust request-body budgets, monitoring/alerting and uptime probes.
3. A live PostgreSQL backup/restore exercise and performance measurement at meaningful scale.
4. Truly blind real-user queries and better ranking/coverage of style, compatibility and asset formats.
5. Automatic backup scheduling, off-device storage and disaster recovery instructions tied to an actual host.

**Proposed Session 7:** confirm and remediate CI issues, improve search with genuine usage examples, and prepare an authenticated, monitored deployment. Selecting a hosting target and provisioning credentials requires a deliberate deployment decision from the project owner.
