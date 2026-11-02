"""Official Poly Haven API adapter. No asset files or preview images are copied."""

from collections import defaultdict, deque
from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from asset_compass.taxonomy import normalize_tag

API_URL = "https://api.polyhaven.com/assets?t=models"
API_TYPES = {"models": (2, "model"), "textures": (1, "texture"), "hdris": (0, "environment")}
SOURCE_URL = "https://polyhaven.com/"
LICENSE_URL = "https://polyhaven.com/license"
TERMS_URL = "https://github.com/Poly-Haven/Public-API/blob/master/ToS.md"
USER_AGENT = "indexAI/0.2 (+https://github.com/Zeaforx/indexAI; asset-link-catalog)"
MAX_RESPONSE_BYTES = 8_000_000


class IngestionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str
    description: str
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
    metadata_source: str = "official_api"
    access: str = "free"
    review_status: str = "approved"
    review_method: str = "automated"
    review_note: str = "Official Poly Haven API metadata; site states CC0. Formats not individually checked."
    record_type: str = "asset"

    def as_import_record(self) -> dict:
        return vars(self).copy()


def fetch_listing(*, asset_type: str = "models", timeout: float = 20.0) -> dict:
    """Fetch one bounded API response with the identifying header required by Poly Haven."""
    if asset_type not in API_TYPES:
        raise ValueError(f"Unknown Poly Haven type: {asset_type}")
    url = f"https://api.polyhaven.com/assets?t={asset_type}"
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            size = response.headers.get("Content-Length")
            if size and int(size) > MAX_RESPONSE_BYTES:
                raise IngestionError("Poly Haven API response exceeds the safe size limit")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise IngestionError(f"Poly Haven API request failed: {exc}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise IngestionError("Poly Haven API response exceeds the safe size limit")
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise IngestionError("Poly Haven API returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise IngestionError("Poly Haven API returned a non-object listing")
    return data


def fetch_model_listing(*, timeout: float = 20.0) -> dict:
    """Backwards-compatible Session 2 model listing."""
    return fetch_listing(asset_type="models", timeout=timeout)


def select_assets(payload: dict, *, asset_type: str = "models", limit: int = 35, query: str = "") -> list[Candidate]:
    """Select diverse model, texture or HDRI links without age penalties."""
    if not 1 <= limit <= 200:
        raise ValueError("Limit must be between 1 and 200")
    if asset_type not in API_TYPES:
        raise ValueError(f"Unknown Poly Haven type: {asset_type}")
    type_id, kind = API_TYPES[asset_type]
    query_words = set(re.findall(r"[a-z0-9]+", query.casefold()))
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for identifier, info in payload.items():
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier):
            continue
        if not isinstance(info, dict) or info.get("type") != type_id:
            continue
        title = info.get("name")
        if not isinstance(title, str) or not title.strip():
            continue
        description = info.get("description") if isinstance(info.get("description"), str) else ""
        raw_tags = [t for t in info.get("tags", []) if isinstance(t, str)] if isinstance(info.get("tags"), list) else []
        raw_categories = [t for t in info.get("categories", []) if isinstance(t, str)] if isinstance(info.get("categories"), list) else []
        raw_category_path = info.get("category") if isinstance(info.get("category"), str) else ""
        searchable = " ".join([title, description, *raw_tags, *raw_categories, raw_category_path]).lower()
        if query_words and not query_words.intersection(re.findall(r"[a-z0-9]+", searchable)):
            continue
        tags = {"3d", kind}
        if asset_type == "textures":
            tags.update({"texture", "material", "pbr"})
        if asset_type == "hdris":
            tags.update({"hdri", "environment", "lighting", "skybox"})
        for raw in (raw_tags + raw_categories)[:20]:
            try:
                tag = normalize_tag(raw)
            except ValueError:
                continue
            if len(tag) <= 100:
                tags.add(tag)
        authors = info.get("authors")
        author_name = ", ".join(list(authors)[:5]) if isinstance(authors, dict) else ""
        category = raw_category_path.partition("/")[0].strip().casefold() or (raw_categories[0].casefold() if raw_categories else "other")
        candidate = Candidate(
            url=f"https://polyhaven.com/a/{quote(identifier)}",
            title=title.strip(), description=description.strip(), dimension="3d", kind=kind,
            tags=sorted(tags), formats=[], source_url=SOURCE_URL, source_name="Poly Haven",
            source_policy_url=LICENSE_URL, license_id="CC0-1.0", license_url=LICENSE_URL,
            license_status="claimed", author_name=author_name,
            source_asset_id=identifier, source_tags=raw_tags,
        )
        groups[category].append(candidate)
    for members in groups.values():
        members.sort(key=lambda item: (item.title.casefold(), item.source_asset_id.casefold()))
    # Round-robin across first-level categories; old assets are not penalized.
    buckets = deque(groups[key] for key in sorted(groups))
    selected: list[Candidate] = []
    while buckets and len(selected) < limit:
        bucket = buckets.popleft()
        selected.append(bucket.pop(0))
        if bucket:
            buckets.append(bucket)
    return selected


def select_models(payload: dict, *, limit: int = 35, query: str = "") -> list[Candidate]:
    """Backwards-compatible model selection."""
    return select_assets(payload, asset_type="models", limit=limit, query=query)

