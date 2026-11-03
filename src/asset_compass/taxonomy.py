"""The small, controlled vocabulary used for the initial 2D/3D catalog."""

import re

DIMENSIONS = frozenset({"2d", "3d", "both"})
KINDS = frozenset({
    "sprite", "tileset", "background", "ui", "model", "environment",
    "animation", "texture", "material", "rig", "collection", "other",
})
ACCESS_TYPES = frozenset({"free", "paid", "mixed", "unknown"})
LICENSE_STATUSES = frozenset({"unknown", "claimed", "verified"})
REVIEW_STATUSES = frozenset({"pending", "approved", "rejected"})
REVIEW_METHODS = frozenset({"none", "automated", "ai-assisted", "human"})

TAG_ALIASES = {
    "low poly": "low-poly", "lowpoly": "low-poly", "pixelated": "pixel-art",
    "pixel art": "pixel-art", "gltf": "gltf", "glb": "glb",
    "pbr textures": "pbr", "spritesheets": "sprite-sheet",
    "spritesheet": "sprite-sheet", "tile set": "tileset",
    "tile sets": "tileset", "isometric art": "isometric",
    "environmental": "environment", "3-d": "3d", "2-d": "2d",
}


def normalize_tag(value: str) -> str:
    """Normalize a user or source tag without inventing new semantics."""
    cleaned = re.sub(r"\s+", " ", value.strip().lower())
    if not cleaned:
        raise ValueError("Tags cannot be empty")
    alias = TAG_ALIASES.get(cleaned)
    if alias:
        return alias
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    if not slug:
        raise ValueError(f"Tag contains no letters or digits: {value!r}")
    if len(slug) > 100:
        raise ValueError("Normalized tags must not exceed 100 characters")
    return slug


def parse_tags(csv: str | None) -> list[str]:
    if not csv:
        return []
    return sorted({normalize_tag(part) for part in csv.split(",") if part.strip()})


def parse_formats(csv: str | None) -> list[str]:
    if not csv:
        return []
    return sorted({normalize_tag(part.removeprefix(".")) for part in csv.split(",") if part.strip()})


def require_choice(value: str, allowed: frozenset[str], field: str) -> str:
    lowered = value.strip().lower()
    if lowered not in allowed:
        raise ValueError(f"Invalid {field}: {value!r}. Choose from: {', '.join(sorted(allowed))}")
    return lowered

