"""Clearly fictional records used to test the workflow without scraping sites."""

from sqlalchemy.orm import Session

from .catalog import add_resource, add_source, review_resource

DEMO = [
    ("Pixel Forest Tileset", "2d", "tileset", "pixel-art,forest,tree,tileset", "png"),
    ("Animated Knight Sprites", "2d", "animation", "pixel-art,character,knight,animated", "png"),
    ("Isometric Dungeon Environment", "2d", "environment", "isometric,dungeon,tileset", "png"),
    ("Fantasy UI Buttons", "2d", "ui", "fantasy,ui,buttons", "png,svg"),
    ("Hand-painted Mountain Background", "2d", "background", "hand-painted,nature,mountain", "png"),
    ("Low Poly Forest Trees", "3d", "model", "low-poly,forest,tree,vegetation", "gltf,glb"),
    ("Modular Sci-Fi Corridor", "3d", "environment", "modular,sci-fi,interior", "fbx,gltf"),
    ("Rigged Robot Character", "3d", "rig", "rigged,character,robot,sci-fi", "blend,fbx"),
    ("PBR Stone Materials", "3d", "material", "pbr,stone,material,tileable", "png"),
    ("Fantasy Creature Animation Pack", "3d", "animation", "fantasy,creature,animated", "fbx"),
]


def seed_demo(session: Session) -> int:
    source, _ = add_source(
        session,
        "https://example.org/demo-assets",
        "DEMO ONLY — Fictional Asset Archive",
        "Synthetic placeholder records, not actual downloadable assets.",
    )
    inserted = 0
    for index, (title, dimension, kind, tags, formats) in enumerate(DEMO, start=1):
        resource, created = add_resource(
            session,
            url=f"https://example.org/demo-assets/item-{index}",
            source_id=source.id,
            title=title,
            description=f"Synthetic demonstration record for {title.lower()}; not a real asset.",
            dimension=dimension,
            kind=kind,
            tags=tags,
            formats=formats,
            access="unknown",
        )
        if created:
            review_resource(
                session, resource.id, status="approved", method="automated",
                note="Synthetic demo fixture only; never treat as a real asset.",
            )
            inserted += 1
    return inserted

