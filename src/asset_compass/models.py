"""Relational data model shared by SQLite and PostgreSQL."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    policy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_url_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_method: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
    attribution_notice: Mapped[str] = mapped_column(Text, default="", nullable=False)
    policy_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    resources: Mapped[list["Resource"]] = relationship(back_populates="source")


class ResourceTag(Base):
    __tablename__ = "resource_tags"

    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("canonical_url", name="uq_resources_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(30), default="asset", nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dimension: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    formats: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    access_type: Mapped[str] = mapped_column(String(10), default="unknown", nullable=False)
    license_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    author_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_asset_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    review_method: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    review_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)

    source: Mapped[Source] = relationship(back_populates="resources")
    tags: Mapped[list[Tag]] = relationship(secondary="resource_tags", lazy="selectin")


def resource_dict(resource: Resource) -> dict[str, Any]:
    return {
        "id": resource.id,
        "title": resource.title,
        "url": resource.canonical_url,
        "source": resource.source.name,
        "source_id": resource.source_id,
        "source_url": resource.source.canonical_url,
        "source_policy_url": resource.source.policy_url,
        "source_attribution_notice": resource.source.attribution_notice,
        "record_type": resource.record_type,
        "description": resource.description,
        "dimension": resource.dimension,
        "kind": resource.kind,
        "tags": sorted(tag.slug for tag in resource.tags),
        "formats": resource.formats,
        "access_type": resource.access_type,
        "license": {
            "id": resource.license_id,
            "url": resource.license_url,
            "status": resource.license_status,
        },
        "author": resource.author_name,
        "source_asset_id": resource.source_asset_id,
        "metadata_source": resource.metadata_source,
        "source_tags": resource.source_tags,
        "review_status": resource.review_status,
        "review_method": resource.review_method,
        "url_status": resource.url_status,
    }

