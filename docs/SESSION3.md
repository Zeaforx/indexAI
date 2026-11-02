# Session 3: Relevance, filtering and source routing

**Implemented 2 November 2026.** This session extends the 45 real curated links from Session 2; no new third-party asset files or previews have been copied.

## Delivered

1. **Explainable lexical search.** A query normalizer removes common instructions such as "find free assets", handles 2D/3D intent, and maps a small, transparent synonym list. Ranking weights matching tags above titles above descriptions, then boosts terms that are distinctive in the current filtered corpus. Each result lists `match_reasons` and its integer score. Results never use publication dates or popularity as a ranking penalty.
2. **PostgreSQL GIN full-text path.** Alembic migration `0003` creates an English `to_tsvector` expression GIN index for titles and descriptions on PostgreSQL only. PostgreSQL search selects candidates through `websearch_to_tsquery` and an `EXISTS` condition for matching normalized tags, then applies the same final scoring as SQLite. Local SQLite uses a metadata scan. Tests compile the PostgreSQL query and inspect the migration's SQL, but **a running PostgreSQL service was unavailable**, so index creation and query execution on a real PostgreSQL database have **not** been verified.
3. **Strict metadata filters.** `dimension`, `kind`, `tag`, `style`, `subject`, `format`, `access`, `license_id` and `license_status` can be applied together. Formats must be explicitly stored; unknown formats never satisfy a format filter. Style and subject are normalized exact-tag filters. `claimed` licenses stay distinct from `verified` licenses.
4. **Source directory routing.** `find-sources` returns the verified Poly Haven model browse page or curated Kenney asset browse destination, their catalog coverage and a transparent distinction between an indexed topical match and dimension-only recommendation. Other manually added sources are routed to their saved homepages, without invented search URLs or implied endorsement. Source recommendations never guarantee a missing asset is present.
5. **Reproducible evaluation.** `data/evaluation_queries.json` contains **33 game-development prompts**, 28 with an expected indexed asset in the top five and five deliberate no-exact-hit source fallbacks. The local evaluation against the Session 2 catalog achieved **33/33**, including **28/28 asset hit@5** and **5/5 source fallback**. These are targeted in-sample tests, not independent measurements of general search quality.

## Run the checks

```bash
uv sync --extra dev
assetindex init
assetindex ingest file data/seed_kenney.json
assetindex ingest file data/seed_polyhaven.json
assetindex evaluate
pytest -q
```

Example queries:

```bash
assetindex search '3d old binoculars' --dimension 3d --json
assetindex search '2d pixel platformer' --style pixel-art --license-status claimed --json
assetindex search '3d flying dragon animation' --with-sources --json
assetindex find-sources '2d zombie sprites' --json
```

## Limits / next session

- Python scoring is designed for a small curated index; benchmark large catalogs and measure PostgreSQL plans before claiming scale. Normalized tag matches outside the SQL candidate set may need further PostgreSQL recall testing as the vocabulary expands.
- No vector embeddings, recrawl scheduler, download-format verification, broken-link scanner, deployment or user accounts exist yet.
- The per-case benchmark tests curated known examples and missing-topic routes. Future evaluation must add blind queries, neutral reviewers, and coverage/precision measures.
- **Session 4:** expose read-only, validated `search_assets` and `find_sources` services through REST and MCP, preserving provenance and license statuses in machine-readable responses.
