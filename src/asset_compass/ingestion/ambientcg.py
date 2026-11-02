"""Bounded ambientCG v3 official API importer; saves links, not asset files."""

from collections import defaultdict, deque
from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from asset_compass.taxonomy import normalize_tag

API_BASE = "https://ambientcg.com/api/v3/assets"
SOURCE_URL = "https://ambientcg.com/"
LICENSE_URL = "https://docs.ambientcg.com/license/"
USER_AGENT = "indexAI/0.5 (+https://github.com/Zeaforx/indexAI; curated-link-index)"
MAX_RESPONSE_BYTES = 2_000_000
ASSET_TYPES = frozenset({"material", "hdri", "3d-model"})
KIND_MAP = {"material": "texture", "hdri": "environment", "3d-model": "model"}


class AmbientCGError(RuntimeError):
    """A failed or malformed *official API* response."""


@dataclass(frozen=True)
class AmbientCandidate:
    url: str
    title: str
    dimension: str
    kind: str
    tags: list[str]
    formats: list[str]
    source_url: str
    source_name: str
    source_policy_url: str
    license_id: str
    license_url: str
    license_status: str
    author_name: str
    source_asset_id: str
    source_tags: list[str]
    description: str = ""
    access: str = "free"
    metadata_source: str = "official_api"
    review_status: str = "approved"
    review_method: str = "automated"
    review_note: str = "Official ambientCG API metadata; publisher states CC0. File formats not checked."
    record_type: str = "asset"

    def as_import_record(self) -> dict:
        return vars(self).copy()


def fetch_listing(
    *, asset_type: str = "material", limit: int = 80, query: str = "", timeout: float = 20.0
) -> dict:
    """Fetch exactly one capped metadata page, without following returned URLs."""
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"Invalid ambientCG type: {asset_type}")
    if not 1 <= limit <= 80:
        raise ValueError("AmbientCG page limit must be 1–80")
    if len(query) > 100:
        raise ValueError("AmbientCG query must be at most 100 characters")
    params = urlencode({
        "type": asset_type, "sort": "popular", "limit": limit,
        "q": query, "include": "type,title,url,tags,shortDescription",
    })
    request = Request(f"{API_BASE}?{params}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if int(response.headers.get("Content-Length") or 0) > MAX_RESPONSE_BYTES:
                raise AmbientCGError("ambientCG response exceeds the size cap")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AmbientCGError(f"ambientCG API request failed: {exc}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AmbientCGError("ambientCG response exceeds the size cap")
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise AmbientCGError("ambientCG API returned invalid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("assets"), list):
        raise AmbientCGError("ambientCG API returned an unexpected listing")
    return data


def select_assets(payload: dict, *, asset_type: str = "material", limit: int = 30) -> list[AmbientCandidate]:
    """Pick distinct asset families first, then fill remaining slots deterministically."""
    if asset_type not in ASSET_TYPES or not 1 <= limit <= 80:
        raise ValueError("Choose a supported ambientCG type and limit between 1 and 80")
    rows = payload.get("assets")
    if not isinstance(rows, list):
        raise AmbientCGError("ambientCG listing must contain an assets array")
    candidates = []
    seen_ids = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != asset_type:
            continue
        identifier = row.get("id")
        title = row.get("title")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,80}", identifier):
            continue
        if not isinstance(title, str) or not title.strip() or identifier in seen_ids:
            continue
        seen_ids.add(identifier)
        raw_tags = [tag for tag in row.get("tags", []) if isinstance(tag, str)] if isinstance(row.get("tags"), list) else []
        tags = {"3d", KIND_MAP[asset_type]}
        if asset_type == "material":
            tags.update({"pbr", "material"})
        elif asset_type == "hdri":
            tags.update({"hdri", "lighting", "skybox"})
        for raw_tag in raw_tags[:30]:
            try:
                tag = normalize_tag(raw_tag)
                if len(tag) <= 100 and not tag.isdigit() and tag.casefold() != identifier.casefold():
                    tags.add(tag)
            except ValueError:
                continue
        candidates.append(AmbientCandidate(
            url=f"https://ambientcg.com/a/{identifier}", title=title.strip(),
            dimension="3d", kind=KIND_MAP[asset_type], tags=sorted(tags), formats=[],
            source_url=SOURCE_URL, source_name="ambientCG", source_policy_url=LICENSE_URL,
            license_id="CC0-1.0", license_url=LICENSE_URL, license_status="claimed",
            author_name="ambientCG", source_asset_id=identifier, source_tags=raw_tags,
        ))
    # Family round-robin avoids a page dominated by brick/wood variants.
    groups: dict[str, list[AmbientCandidate]] = defaultdict(list)
    for item in candidates:
        family = re.sub(r"\d.*$", "", item.source_asset_id).casefold()
        groups[family].append(item)
    for bucket in groups.values():
        bucket.sort(key=lambda item: (item.source_asset_id.casefold(), item.title.casefold()))
    buckets = deque(groups[family] for family in sorted(groups))
    selected = []
    while buckets and len(selected) < limit:
        bucket = buckets.popleft()
        selected.append(bucket.pop(0))
        if bucket:
            buckets.append(bucket)
    return selected
