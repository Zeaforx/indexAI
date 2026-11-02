# Session 4: Read-only REST and MCP discovery interfaces

**Implemented 2 November 2026.** Builds on the reviewed 45-link 2D/3D catalog from Session 2 and the ranking/source-routing work from Session 3. This is a local prototype, **not a public deployment**.

## Delivered

- `assetindex-api` starts a local FastAPI ASGI app on `127.0.0.1:8000` (port overridable with `ASSET_COMPASS_PORT`). A built-in OpenAPI schema and interactive documentation describe filters and response contracts.
- `GET /healthz` checks catalog table availability and reports resource/source counts; `GET /v1/assets/search?q=...` returns ranked, approved links and automatically includes directory suggestions when no link matches; `GET /v1/sources/search?q=...` searches curated source directories; `GET /v1/assets/{id}` returns one approved item or 404.
- MCP SDK v2 implements three **read-only** tools: `search_assets`, `find_sources`, and `get_asset`. They share the exact REST query service, use typed MCP input constraints and return structured result data. The agent also receives the tool's `readOnlyHint` and `openWorldHint=false` annotations.
- MCP Streamable HTTP is mounted at `/mcp` in the REST server, with the required session manager managed by the host lifespan. A separate `assetindex-mcp` stdio entry point uses the same tools for local AI clients.
- Every resource retains the source name, source homepage, source policy URL, source attribution notice, license identifier/evidence/status, review method, and original canonical URL. Unknown formats stay unknown. Pending/rejected records cannot be retrieved through REST or MCP tools.
- Database error responses are sanitized; malformed query arguments use 422 in REST and recoverable tool errors in MCP. The REST and MCP interfaces expose **no curator mutation**, file download, arbitrary URL fetch, arbitrary SQL, import or crawling command.

## Start locally

```bash
uv sync --extra dev
uv run assetindex init
uv run assetindex ingest file data/seed_kenney.json
uv run assetindex ingest file data/seed_polyhaven.json
uv run assetindex-api
```

Then open <http://127.0.0.1:8000/docs>, run one of the example `curl` requests in the README, or connect an MCP client to <http://127.0.0.1:8000/mcp> (Streamable HTTP). For MCP stdio, configure a host to launch `assetindex-mcp` with the database location in `ASSET_COMPASS_DB_URL`.

Sample response from REST search (abbreviated):

```json
{
  "query": "3d flying dragon animation",
  "count": 0,
  "resources": [],
  "sources": [{
    "name": "Poly Haven",
    "browse_url": "https://polyhaven.com/models",
    "indexed_matches": 0,
    "match_basis": "dimension coverage only"
  }],
  "fallback_used": true,
  "rights_notice": "Results are destination links, not asset downloads. License status 'claimed' is a provider claim, not independent verification. Check each source before use."
}
```

Every source directory result also includes a `verification_notice`. This fallback is *not* proof that a dragon animation exists on Poly Haven.

## Verification

- **36/36 automated tests passed** across all sessions. The pre-existing 33-case relevance benchmark remains **33/33** on the seeded catalog; the Python sdist and wheel build successfully.
- REST integration tests use an isolated real SQLite catalog, import both official-source seed files, and verify rank, license provenance, no-hit routing, source listing, record details, input validation, 404/422/503 errors and read-only behavior.
- MCP Streamable HTTP is exercised using actual JSON-RPC `initialize`, `tools/list`, and `tools/call` requests. Tests confirm read-only annotations, structured link results, source fallback, invalid argument errors and denial of pending records.
- The stdio entry-point configuration is checked, but no successful end-to-end stdio subprocess exchange is claimed: the execution environment's asynchronous pipe/thread integration hung during the attempt. The HTTP MCP protocol works and uses the **same SDK server and tools**.
- The previous 33-query search benchmark continues to run against the real seeded links. No live external API, browser crawling or PostgreSQL server was required for these tests.

## Security and remaining work

- Default bind is local-loopback only; the MCP transport retains its localhost DNS-rebinding protection. CORS is not opened. Nothing in this build authorizes internet-facing use. If deployment becomes necessary, first add authenticated access, request limits, TLS, monitoring, least-privilege database access and verified hostname/origin policies.
- Current SQLAlchemy query functions are synchronous and operate on a small catalog; benchmark load and introduce async/offloaded database work when scaling.
- There are still only 45 link records, no link-health scanner, no independent per-file license audit, no production database backup/restore service and no user-facing hosted frontend.
- Next session: expand specialist 2D/3D sources within their publishing policies, add safe scheduled link checks, and improve catalog coverage and data quality without scraping prohibited content.
