# Source policy notes — checked 2 November 2026

This project indexes **links and annotations**, not third-party files. Policies can change. Recheck these primary sources before scaling an importer or publishing a new dataset.

## Poly Haven — official API integration

- API: <https://api.polyhaven.com/assets?t=models> (also `?t=textures` and `?t=hdris`)
- API overview: <https://polyhaven.com/our-api>
- API terms: <https://github.com/Poly-Haven/Public-API/blob/master/ToS.md>
- Asset license statement: <https://polyhaven.com/license>
- Method: a single official API call, with a unique identifying User-Agent and a bounded response size; no asset downloads or image mirroring.
- Attribution: the terms for using the **live API** require visible indication that results come from Poly Haven. We store the source name and `Powered by Poly Haven` notice; any later UI or agent response must keep the source name visible.
- License status: imported entries store `CC0-1.0`, a license evidence URL, and status **`claimed`**, not `verified`. This denotes the original provider's site-wide license claim; it does not certify each individual file or downstream compatibility.
- Formats: the listing endpoint does not enumerate per-asset download formats, so formats are left empty until verified from an individual asset page or `/files/{id}` response.
- Maintenance: respect rate limits and API changes, avoid aggressive polling, and retain source identity when surfacing live API data.
- Session 5 adds a separately exported, 18-link **texture** snapshot (`data/seed_polyhaven_textures.json`), selected across source categories. This does not guarantee that a current download is available or any particular texture format.

## ambientCG — official v3 API integration

- Official API documentation: <https://docs.ambientcg.com/api/v3/assets/>
- API endpoint: <https://ambientcg.com/api/v3/assets>
- Official asset-license explanation: <https://docs.ambientcg.com/license/>
- Source browsing directory: <https://ambientcg.com/list>
- Method: one bounded API metadata request for `material`, `hdri` or `3d-model`; at most 80 results are read per request. Only official asset-page URLs of the form `https://ambientcg.com/a/{id}` are stored, not original file downloads, thumbnails or previews.
- License: the site identifies its assets as CC0; the importer stores `CC0-1.0` with status **`claimed`**. Asset-specific availability and rights are not independently verified.
- Formats: unknown. PBR, material and category labels describe the provider's metadata and broad asset type, **not** a confirmed downloadable file format or a validated PBR texture set.
- Attribution: source name `ambientCG` and notice `Assets from ambientCG` are retained for transparent discovery, without implying endorsement.
- Session 5 snapshot: 30 diverse materials (`data/seed_ambientcg_materials.json`) selected from a live official API listing. The importer supports HDRI and model categories but they are **not** included in this seed.

## Kenney — manually selected pack pages

- Official assets: <https://kenney.nl/assets>
- Licensing FAQ: <https://kenney.nl/support>
- Method: individually identified asset/pack links in `data/seed_kenney.json` (10) and `data/seed_kenney_expansion.json` (17). **No automated crawler or scraper.** Session 5 includes UI, tilesets, background art, sprites and 3D animated character packs, including older published packs.
- License: selected official pack pages indicate Creative Commons CC0. We preserve a per-page evidence URL and mark status `claimed`; the user should confirm the page's current license before use.
- Formats: not inferred from the category; remain unknown until independently checked. The `Input Prompts` entry alone carries `png` and `svg`, supported by Kenney's own [Input Prompts knowledge-base article](https://kenney.nl/knowledge-base/game-assets-2d/using-input-prompts).
- Review: records are marked `ai-assisted`, never misrepresented as human-reviewed.

## Other sources deliberately deferred

- OpenGameArt: licenses vary by individual submission; preview images may have different rights. Not crawled or indexed in this session. <https://lpc.opengameart.org/content/faq>
- Quaternius: the current general asset license has distribution restrictions and can conflict with older references to CC0. Not indexed until precise per-pack rights are evaluated. <https://quaternius.com/license.html>

No source affiliation or endorsement is implied. Our MIT source-code license does not automatically apply to other sites' metadata or asset files.

## Link health is a limited observation, not proof

`assetindex check-links` previews up to 20 approved URLs and makes **no requests** by default. `--execute` enables sequential `HEAD` requests only for `kenney.nl`, `polyhaven.com` and `ambientcg.com` over HTTPS on the default port. The checker verifies that DNS currently resolves to public addresses, does not follow redirects or fall back to `GET`, and uses a 24-hour recheck interval unless `--force` is explicitly given. It may report `healthy`, `redirect`, `suspect_missing`, `restricted`, `unsupported`, `transient_error` or `skipped`.

A `404` or `410` response to `HEAD` is labelled `suspect_missing`, **not** a definitive missing asset. Rate limiting, anti-bot restrictions, HEAD-method limitations and redirects can all be legitimate. Records are neither removed nor rejected automatically. This tool is not a substitute for manual review of direct asset pages and downloads.

