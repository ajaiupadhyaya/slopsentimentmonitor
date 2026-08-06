"""Ingestion and enrichment.

Two independently runnable stages:

* `ingest` — collectors → `documents`. Idempotent on `(source, external_id)`,
  so running it every ten minutes updates scores rather than duplicating rows.
* `enrich` — unenriched `documents` → `mentions` + `sentiments`. Separate
  because analysis improves faster than data arrives; re-running it against the
  stored corpus costs no network calls.

A failing collector is contained: it is logged and reported in the summary, and
the other sources still land their data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pulseai.collectors.base import Collector, RawDocument
from pulseai.collectors.github import GitHubCollector
from pulseai.collectors.hackernews import HackerNewsCollector
from pulseai.collectors.reddit import RedditCollector
from pulseai.collectors.rss import RSSCollector
from pulseai.config import Settings, get_settings
from pulseai.db import session_scope
from pulseai.models import Document, Mention, Model, Sentiment, Source
from pulseai.pipeline.analyze import Analyzer, aspect_text, get_analyzer
from pulseai.pipeline.clean import clean
from pulseai.pipeline.detect import ModelDetector
from pulseai.registry import Alias, ModelSpec

log = structlog.get_logger(__name__)


@dataclass
class SourceResult:
    source: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_reason: str | None = None
    error: str | None = None


@dataclass
class IngestReport:
    results: list[SourceResult] = field(default_factory=list)

    @property
    def total_fetched(self) -> int:
        return sum(r.fetched for r in self.results)

    @property
    def total_inserted(self) -> int:
        return sum(r.inserted for r in self.results)

    def render(self) -> str:
        lines = []
        for result in self.results:
            if result.skipped_reason:
                lines.append(f"  {result.source:<12} skipped — {result.skipped_reason}")
            elif result.error:
                lines.append(f"  {result.source:<12} FAILED — {result.error}")
            else:
                lines.append(
                    f"  {result.source:<12} {result.fetched:>5} fetched  "
                    f"{result.inserted:>5} new  {result.updated:>5} updated"
                )
        return "\n".join(lines)


def default_collectors(settings: Settings | None = None) -> list[Collector]:
    settings = settings or get_settings()
    return [
        HackerNewsCollector(settings),
        RSSCollector(settings),
        GitHubCollector(settings),
        RedditCollector(settings),
    ]


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


async def ingest(
    collectors: list[Collector] | None = None,
    limit_per_source: int = 200,
    settings: Settings | None = None,
) -> IngestReport:
    settings = settings or get_settings()
    collectors = collectors if collectors is not None else default_collectors(settings)
    report = IngestReport()

    async with session_scope() as session:
        source_ids = await _source_ids(session)

    for collector in collectors:
        result = SourceResult(source=collector.name)
        report.results.append(result)

        available, reason = collector.available()
        if not available:
            result.skipped_reason = reason
            log.info("ingest.skipped", source=collector.name, reason=reason)
            continue

        source_id = source_ids.get(collector.name)
        if source_id is None:
            result.error = "source row missing; run `pulseai seed` first"
            continue

        try:
            async with collector:  # type: ignore[attr-defined]
                batch: list[RawDocument] = []
                async for document in collector.collect(limit_per_source):
                    batch.append(document)
                    result.fetched += 1
                    if len(batch) >= 100:
                        await _persist(batch, source_id, result)
                        batch = []
                if batch:
                    await _persist(batch, source_id, result)
        except Exception as exc:
            # One dead source must not cost us the others' data.
            result.error = f"{type(exc).__name__}: {exc}"
            log.warning("ingest.failed", source=collector.name, error=str(exc))

    log.info(
        "ingest.complete", fetched=report.total_fetched, inserted=report.total_inserted
    )
    return report


async def _source_ids(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(Source.name, Source.id))
    return dict(rows.all())  # type: ignore[arg-type]


async def _persist(batch: list[RawDocument], source_id: int, result: SourceResult) -> None:
    """Upsert on the natural key so re-collection refreshes rather than duplicates."""
    if not batch:
        return

    payload = [
        {
            "source_id": source_id,
            "external_id": doc.external_id,
            "url": doc.url,
            "author": doc.author,
            "title": doc.title,
            "content": doc.content or "",
            "published_at": doc.published_at,
            "score": doc.score,
            "views": doc.views,
            "likes": doc.likes,
            "shares": doc.shares,
            "comment_count": doc.comment_count,
            "raw_json": doc.raw,
        }
        for doc in batch
    ]

    async with session_scope() as session:
        statement = pg_insert(Document).values(payload)
        statement = statement.on_conflict_do_update(
            constraint="uq_documents_source_external",
            set_={
                # Engagement numbers move after publication.
                "score": statement.excluded.score,
                "likes": statement.excluded.likes,
                "comment_count": statement.excluded.comment_count,
                # Text is refreshed too, so that improving a collector's parsing
                # heals the stored corpus on the next run instead of leaving
                # badly-extracted documents in place forever.
                "title": statement.excluded.title,
                "content": statement.excluded.content,
                # Healing the text without clearing this would leave the old
                # mentions and sentiment attached to content that no longer
                # exists. Changed text means the analysis is stale.
                "enriched_at": case(
                    (Document.content.is_distinct_from(statement.excluded.content), None),
                    else_=Document.enriched_at,
                ),
            },
        ).returning(Document.id, Document.created_at, Document.enriched_at)
        rows = (await session.execute(statement)).all()

    # A row whose created_at predates this batch was an update, not an insert.
    now = datetime.now(UTC)
    for _, created_at, _ in rows:
        if created_at is not None and (now - created_at).total_seconds() < 5:
            result.inserted += 1
        else:
            result.updated += 1


# ---------------------------------------------------------------------------
# Enrich
# ---------------------------------------------------------------------------


async def build_detector(session: AsyncSession) -> ModelDetector:
    """Compile the matcher from the database, not the static registry.

    This is what makes models addable at runtime: insert a row with aliases and
    the next enrichment run picks it up.
    """
    rows = (
        await session.execute(select(Model).where(Model.active.is_(True)))
    ).scalars().all()

    entries: list[tuple[str, str, str, Alias]] = []
    for row in rows:
        spec = ModelSpec(
            slug=row.slug,
            name=row.name,
            company=row.company,
            website=row.website,
            aliases=tuple(Alias(**alias) for alias in (row.aliases or [])),
        )
        entries.extend(
            (spec.slug, spec.name, spec.company, alias) for alias in spec.all_aliases()
        )
    return ModelDetector(entries)


async def enrich(
    batch_size: int = 200,
    max_documents: int | None = None,
    reprocess: bool = False,
    analyzer: Analyzer | None = None,
) -> dict[str, int]:
    """Detect models and score sentiment for documents awaiting analysis."""
    analyzer = analyzer or get_analyzer()
    stats = {"documents": 0, "mentions": 0, "sentiments": 0}

    async with session_scope() as session:
        detector = await build_detector(session)
        model_ids = dict(
            (await session.execute(select(Model.slug, Model.id))).all()  # type: ignore[arg-type]
        )

    processed = 0
    while max_documents is None or processed < max_documents:
        take = batch_size
        if max_documents is not None:
            take = min(batch_size, max_documents - processed)

        async with session_scope() as session:
            query = select(Document).order_by(Document.published_at.desc()).limit(take)
            if not reprocess:
                query = query.where(Document.enriched_at.is_(None))
            else:
                query = query.offset(processed)
            documents = (await session.execute(query)).scalars().all()

            if not documents:
                break

            for document in documents:
                counts = await _enrich_one(session, document, detector, analyzer, model_ids)
                stats["mentions"] += counts[0]
                stats["sentiments"] += counts[1]
                stats["documents"] += 1
                processed += 1

    log.info("enrich.complete", **stats)
    return stats


async def _enrich_one(
    session: AsyncSession,
    document: Document,
    detector: ModelDetector,
    analyzer: Analyzer,
    model_ids: dict[str, int],
) -> tuple[int, int]:
    # Strip machine attribution before anything reads the text. Skipping this
    # attributed 18.6% of mentions in the first live corpus to robot signatures
    # and scored them against the sentiment of unrelated commits.
    cleaned = clean(document.searchable_text, document.author)
    text = cleaned.text
    mentions = [] if cleaned.is_bot_authored else detector.detect(text)

    # Replace rather than merge: enrichment must be idempotent so it can be
    # re-run after the detector or analyzer improves.
    await session.execute(delete(Mention).where(Mention.document_id == document.id))
    await session.execute(delete(Sentiment).where(Sentiment.document_id == document.id))

    mention_count = 0
    sentiment_count = 0

    for mention in mentions:
        model_id = model_ids.get(mention.slug)
        if model_id is None:
            continue

        session.add(
            Mention(
                document_id=document.id,
                model_id=model_id,
                confidence=mention.confidence,
                position=mention.start,
                occurrences=mention.count,
            )
        )
        mention_count += 1

        # Score only the text around this model's own mentions, so a comparison
        # post is positive about one model and negative about the other.
        window = aspect_text(text, [(mention.start, mention.end)])
        score = analyzer.score(window)
        session.add(
            Sentiment(
                document_id=document.id,
                model_id=model_id,
                positive=score.positive,
                negative=score.negative,
                neutral=score.neutral,
                confidence=score.confidence,
                compound=score.compound,
                analyzer=score.analyzer,
            )
        )
        sentiment_count += 1

    document.enriched_at = datetime.now(UTC)
    return mention_count, sentiment_count


async def pending_count() -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(func.count()).select_from(Document).where(Document.enriched_at.is_(None))
        )
        return int(result.scalar_one())
