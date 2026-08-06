"""Database schema.

Follows the README's table layout, with two deliberate additions:

* `documents.external_id` — collectors are re-run constantly and must be
  idempotent. `(source_id, external_id)` is the natural key that makes
  re-ingesting a Hacker News thread update rows instead of duplicating them.
* `documents.enriched_at` — separates "we have this document" from "we have
  analysed it", so enrichment can be re-run when models improve without
  re-fetching anything.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Model(Base):
    """A tracked LLM. Seeded from registry.py, editable at runtime."""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    company: Mapped[str] = mapped_column(String(128), index=True)
    website: Mapped[str | None] = mapped_column(String(512))
    #: Serialised Alias records; detection rebuilds its matcher from these.
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    mentions: Mapped[list[Mention]] = relationship(back_populates="model")


class Source(Base):
    """An upstream platform we collect from."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    documents: Mapped[list[Document]] = relationship(back_populates="source")


class Document(Base):
    """One post, comment, issue, or article."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_documents_source_external"),
        Index("ix_documents_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    #: Stable identifier within the source. Makes ingestion idempotent.
    external_id: Mapped[str] = mapped_column(String(255))

    url: Mapped[str | None] = mapped_column(String(1024))
    author: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    language: Mapped[str | None] = mapped_column(String(8))

    score: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    comment_count: Mapped[int | None] = mapped_column(Integer)

    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    #: NULL means the enrichment pipeline has not processed this yet.
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    source: Mapped[Source] = relationship(back_populates="documents")
    mentions: Mapped[list[Mention]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    sentiments: Mapped[list[Sentiment]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    @property
    def searchable_text(self) -> str:
        return f"{self.title or ''}\n{self.content or ''}".strip()


class Mention(Base):
    """A model referenced by a document."""

    __tablename__ = "mentions"
    __table_args__ = (
        UniqueConstraint("document_id", "model_id", name="uq_mentions_document_model"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    #: Character offset of the first occurrence, for highlighting in the UI.
    position: Mapped[int] = mapped_column(Integer, default=0)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)

    document: Mapped[Document] = relationship(back_populates="mentions")
    model: Mapped[Model] = relationship(back_populates="mentions")


class Sentiment(Base):
    """Sentiment toward one model within one document.

    Keyed per (document, model) rather than per document, because a comparison
    post is positive about one model and negative about another.
    """

    __tablename__ = "sentiments"
    __table_args__ = (
        UniqueConstraint("document_id", "model_id", name="uq_sentiments_document_model"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)

    positive: Mapped[float] = mapped_column(Float, default=0.0)
    negative: Mapped[float] = mapped_column(Float, default=0.0)
    neutral: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    #: positive - negative, in [-1, 1]. Denormalised because every timeseries
    #: query averages it and computing it in SQL each time is wasteful.
    compound: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    analyzer: Mapped[str] = mapped_column(String(32), default="heuristic")

    document: Mapped[Document] = relationship(back_populates="sentiments")
    model: Mapped[Model] = relationship()
