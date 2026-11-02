"""Explainable, deterministic lexical relevance for a small curated catalog.

The same scoring is used after SQLite scans and PostgreSQL FTS candidate selection.
No date or popularity signals are used: useful old links are first-class results.
"""

import re
from math import log2

from .models import Resource

STOPWORDS = frozenset({
    "a", "an", "and", "are", "asset", "assets", "at", "build", "can", "create",
    "collection", "download", "find", "for", "free", "from", "game", "games", "get", "give",
    "i", "in", "is", "it", "looking", "make", "me", "my", "need", "of", "on",
    "links", "model", "models", "pack", "please", "project", "resource", "resources",
    "some", "that", "the", "this", "to", "use", "using", "want", "with", "you", "2d", "3d",
})

# Category words alone must not pretend to match an unindexed subject. For
# example, "flying dragon animation" should not return an unrelated animation.
GENERIC_ASSET_TERMS = frozenset({
    "animation", "background", "character", "environment", "hdri", "icon",
    "lighting", "material", "model", "pbr", "rig", "skybox", "sprite",
    "texture", "tileset", "ui",
})

TERM_ALIASES = {
    "lowpoly": "low-poly", "pixelart": "pixel-art", "pixel": "pixel-art", "pixelated": "pixel-art",
    "spritesheets": "sprite-sheet", "spritesheet": "sprite-sheet",
    "tiles": "tileset", "tile": "tileset", "tilemap": "tileset", "tilemaps": "tileset",
    "tilesets": "tileset", "trees": "tree", "forests": "forest",
    "woods": "forest", "woodland": "forest", "woodlands": "forest",
    "animations": "animation", "animated": "animation",
    "sprites": "sprite", "characters": "character", "environments": "environment",
    "models": "model", "textures": "texture", "materials": "material",
    "props": "prop", "rocks": "rock", "stones": "stone", "buildings": "building",
    "weapons": "weapon", "vehicles": "vehicle", "chairs": "chair",
}


def _tokens(value: str) -> list[str]:
    cleaned = value.casefold()
    cleaned = re.sub(r"\blow[\s-]+poly\b", "lowpoly", cleaned)
    cleaned = re.sub(r"\bpixel[\s-]+art\b", "pixelart", cleaned)
    cleaned = re.sub(r"\bsprite[\s-]+sheets?\b", "spritesheet", cleaned)
    return [TERM_ALIASES.get(term, term) for term in re.findall(r"[a-z0-9]+", cleaned)]


def query_terms(query: str) -> set[str]:
    """Normalize a prompt into searchable concepts, not incidental instruction words."""
    return set(_tokens(query)) - STOPWORDS


def infer_dimension(query: str) -> str | None:
    """Honor explicit 2D/3D intent without claiming to infer it from subject matter."""
    tokens = set(re.findall(r"\b(?:2d|3d)\b", query.casefold()))
    return next(iter(tokens)) if len(tokens) == 1 else None


def index_terms(text: str) -> set[str]:
    return set(_tokens(text))


def searchable_terms(resource: Resource) -> set[str]:
    return (
        index_terms(resource.title) | index_terms(resource.description)
        | index_terms(resource.kind)
        | set().union(*(index_terms(tag.slug) for tag in resource.tags))
    )


def rarity_weights(resources: list[Resource], terms: set[str]) -> dict[str, float]:
    """Discount common words in the *catalog*, favoring distinctive subjects."""
    occurrences = {term: 0 for term in terms}
    for resource in resources:
        observed = searchable_terms(resource)
        for term in terms & observed:
            occurrences[term] += 1
    count = len(resources)
    return {term: 1 + log2((count + 1) / (frequency + 1)) for term, frequency in occurrences.items()}


def score_resource(
    resource: Resource, terms: set[str], weights: dict[str, float] | None = None
) -> tuple[int, list[str]]:
    """Return an integer score and verifiable match explanations."""
    if not terms:
        return 0, ["filtered catalog listing"]
    title = index_terms(resource.title)
    tags = set().union(*(index_terms(tag.slug) for tag in resource.tags))
    description = index_terms(resource.description)
    kind = index_terms(resource.kind)
    matched_tags = terms & tags
    matched_titles = terms & title
    matched_descriptions = terms & description
    matched_kinds = terms & kind
    distinctive = terms - GENERIC_ASSET_TERMS
    if distinctive and not distinctive.intersection(
        matched_tags | matched_titles | matched_descriptions | matched_kinds
    ):
        return 0, []
    weight = weights or {}
    score = round(sum(
        multiplier * weight.get(term, 1)
        for multiplier, matches in (
            (9, matched_tags), (6, matched_titles),
            (2, matched_descriptions), (1, matched_kinds),
        )
        for term in matches
    ))
    reasons = (
        [f"tag:{term}" for term in sorted(matched_tags)]
        + [f"title:{term}" for term in sorted(matched_titles)]
        + [f"description:{term}" for term in sorted(matched_descriptions - matched_titles)]
        + [f"kind:{term}" for term in sorted(matched_kinds - matched_tags - matched_titles)]
    )
    return score, reasons
