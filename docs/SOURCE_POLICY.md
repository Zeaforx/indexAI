# Source policy notes — checked 2 November 2026

This project indexes **links and annotations**, not third-party files. Policies can change. Recheck these primary sources before scaling an importer or publishing a new dataset.

## Poly Haven — official API integration

- API: <https://api.polyhaven.com/assets?t=models>
- API overview: <https://polyhaven.com/our-api>
- API terms: <https://github.com/Poly-Haven/Public-API/blob/master/ToS.md>
- Asset license statement: <https://polyhaven.com/license>
- Method: a single official API call, with a unique identifying User-Agent and a bounded response size; no asset downloads or image mirroring.
- Attribution: the terms for using the **live API** require visible indication that results come from Poly Haven. We store the source name and `Powered by Poly Haven` notice; any later UI or agent response must keep the source name visible.
- License status: imported entries store `CC0-1.0`, a license evidence URL, and status **`claimed`**, not `verified`. This denotes the original provider's site-wide license claim; it does not certify each individual file or downstream compatibility.
- Formats: the listing endpoint does not enumerate per-asset download formats, so formats are left empty until verified from an individual asset page or `/files/{id}` response.
- Maintenance: respect rate limits and API changes, avoid aggressive polling, and retain source identity when surfacing live API data.

## Kenney — manually selected pack pages

- Official assets: <https://kenney.nl/assets>
- Licensing FAQ: <https://kenney.nl/support>
- Method: a small set of individually identified asset/pack links, saved in `data/seed_kenney.json`. **No automated crawler or scraper.**
- License: selected official pack pages indicate Creative Commons CC0. We preserve a per-page evidence URL and mark status `claimed`; the user should confirm the page's current license before use.
- Formats: not inferred from the category; remain unknown until independently checked.
- Review: records are marked `ai-assisted`, never misrepresented as human-reviewed.

## Other sources deliberately deferred

- OpenGameArt: licenses vary by individual submission; preview images may have different rights. Not crawled or indexed in this session. <https://lpc.opengameart.org/content/faq>
- Quaternius: the current general asset license has distribution restrictions and can conflict with older references to CC0. Not indexed until precise per-pack rights are evaluated. <https://quaternius.com/license.html>

No source affiliation or endorsement is implied. Our MIT source-code license does not automatically apply to other sites' metadata or asset files.

