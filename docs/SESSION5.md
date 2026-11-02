# Build Session 5 — catalog coverage, cautious link health, evaluation

Completed locally: **2 November 2026**. This is an index of **external asset-page links and annotations**, not a hosted asset collection. Work was executed by the assistant and verified with local tests. Source policies and live API metadata were reviewed, but individual asset downloads were not mirrored or exhaustively checked.

## Deliverables

| Deliverable | Result |
| --- | --- |
| Larger offline catalog | **110 unique approved resource-page URLs** from 3 publishers; reproducible JSON seeds |
| Kenney variety | 27 curated 2D and 3D pack pages in two snapshots; UI, backgrounds, sprites, maps, isometric tiles, animated characters |
| Poly Haven variety | 35 model pages plus **18 texture pages** selected from an official API response |
| ambientCG importer | New bounded official v3 metadata adapter; **30 material pages** saved from one live listing, spread across families |
| Typed source import | `polyhaven --type models\|textures\|hdris` and `ambientcg --type material\|hdri\|3d-model`; dry-run supported |
| Safe, inspectable link health | Default preview; explicit `--execute` writes HEAD observations, never deletes/rejects links |
| Improved relevance | Unrelated animation/model matches no longer count merely because a generic category word overlaps; source routing considers category coverage |
| Expanded evaluation | **32/32** local, in-sample scenarios pass, including 27 asset-hit and 5 source-fallback prompts |
| Database migration | Alembic `0004` adds `last_checked_at` and `last_http_status`; preserves old records |

### Snapshot composition

| Source | Snapshot | Links | Dimension / categories |
| --- | --- | ---: | --- |
| Kenney | `data/seed_kenney.json` | 10 | 2D curated packs |
| Poly Haven | `data/seed_polyhaven.json` | 35 | 3D models |
| Kenney | `data/seed_kenney_expansion.json` | 17 | 2D UI, sprite, background and tileset packs; 3D character animation packs |
| ambientCG | `data/seed_ambientcg_materials.json` | 30 | 3D PBR material/texture pages |
| Poly Haven | `data/seed_polyhaven_textures.json` | 18 | 3D material/texture pages |
| **Total** | | **110** | |

Snapshots were exported from local imported metadata or carefully selected official pack pages. IDs, titles, source links and source-claimed license metadata are stored; no thumbnails, full third-party descriptions, or asset downloads are bundled. Links may become unavailable later. File formats generally remain unknown and are never guessed from an asset category; Kenney's `Input Prompts` pack has independently documented PNG/SVG format evidence.

### Source and rights provenance

- Poly Haven official API overview: <https://polyhaven.com/our-api>; live API terms: <https://github.com/Poly-Haven/Public-API/blob/master/ToS.md>; license: <https://polyhaven.com/license>.
- ambientCG official v3 API: <https://docs.ambientcg.com/api/v3/assets/>; asset license statement: <https://docs.ambientcg.com/license/>.
- Kenney pack catalog: <https://kenney.nl/assets>; licensing FAQ: <https://kenney.nl/support>; Input Prompts formats: <https://kenney.nl/knowledge-base/game-assets-2d/using-input-prompts>.

Every snapshot record identifies its publisher and records `CC0-1.0` only as **`claimed`**. This is not independent legal verification; users must review the live asset page and its licensing before use. The source attribution fields must stay visible to agent consumers. See [source policy details](SOURCE_POLICY.md).

## Reproduce in a clean local database

From the repository directory, with `uv` and Python 3.12+ installed:

```bash
uv sync --extra dev
export ASSET_COMPASS_DB_URL='sqlite:///session5.sqlite3'
uv run assetindex init
uv run assetindex ingest file data/seed_kenney.json
uv run assetindex ingest file data/seed_polyhaven.json
uv run assetindex ingest file data/seed_kenney_expansion.json
uv run assetindex ingest file data/seed_ambientcg_materials.json
uv run assetindex ingest file data/seed_polyhaven_textures.json
uv run assetindex evaluate data/evaluation_queries_expanded.json
uv run assetindex search '3d PBR wood floor texture' --json
uv run assetindex search '3d flying dragon animations' --with-sources --json
uv run assetindex check-links --limit 5
uv run pytest -q
```

The local expanded benchmark output was:

```
Search benchmark: 32/32 scenarios passed
Asset hit@5: 100.0%; source fallback: 100.0%
```

**Interpretation:** These are authored queries against known seeded records and five deliberate misses. They confirm the intended feature behavior, **not** search quality on unseen prompts, coverage of all game assets, or a semantic-retrieval guarantee. The former 33-query benchmark in `data/evaluation_queries.json` belongs to the original 45-link snapshot and includes fallback expectations that naturally change once new resources are added.

## Link-health safety and limits

```bash
uv run assetindex check-links --limit 10                   # preview, no network writes
uv run assetindex check-links --source Kenney --limit 5    # preview a source
uv run assetindex check-links --source Kenney --limit 5 --execute  # live HEAD observations
```

- Checks only approved records, at most 20 per run; sort unchecked first, then oldest checked.
- Only HTTPS URLs on publisher hosts `kenney.nl`, `polyhaven.com`, `ambientcg.com` are eligible; reject non-default ports, URL credentials, private DNS results and unexpected publisher domains.
- Only `HEAD`, identifying User-Agent, short timeout, no redirects and no `GET` fallback. Sequential calls include a 250 ms spacing; repeat checks normally wait 24 hours. `--force --execute` is an explicit recheck override.
- Store `url_status`, optional HTTP status and UTC observation time. A 404/410 is **`suspect_missing`**, not proof of permanently missing files; 401/403/429 are **`restricted`**; 405/501 are **`unsupported`**.
- Health checks **never** delete, automatically reject or revise source license metadata. Operators need human confirmation for questionable pages. No live batch HEAD verification was performed when creating these snapshots.

## Verification and limitations

Executed automated tests cover both official API adapters with network mocks, cap/type validation, all five offline snapshots and idempotence, 110-record retrieval, 32-query evaluation, HEAD safety and response classification, default preview, cooldown and forced checks, preserved curation state, CLI validation, and upgrade from migration `0003` to `0004`. The broader test suite also covers REST and MCP behavior from prior sessions.

Not yet done:

1. No public deployment, auth, abuse protection or public rate limiting; current REST/MCP services must stay bound to localhost.
2. PostgreSQL FTS migration logic has been compiled but not tested against a live PostgreSQL instance; all Session 5 checks use SQLite.
3. No sustained live API/HEAD rate testing and no complete per-link availability audit. Publisher responses, especially to `HEAD`, may vary.
4. Snapshot metadata is uneven: per-asset format, quality, poly count, animation format, render preview, and real download URL are often unknown. Avoid fabricating them.
5. Benchmark is hand-authored and in-sample. Session 6 should add a blind test set, production guards, backup/restore automation and rate limiting before hosting.

## Proposed next build session

**Session 6 — Operational safety and recoverability:** independent unseen query evaluation, read-only API throttling and abuse protections, Postgres integration testing (where a test server is available), repeatable backup and restore tests, environment/secrets review, CI verification, and explicit deployment readiness checklist. Deployment can be a later, separate session after a hosting target and credentials are provided.
