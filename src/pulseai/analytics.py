"""Aggregate queries behind the API.

Two rules run through all of it:

* **Confidence-weight the averages.** A mention detected at 0.56 confidence
  should not move a model's sentiment as much as one detected at 1.0. Every
  average here is weighted by `mention.confidence * sentiment.confidence`.
* **Report the denominator.** Every figure ships with the mention count that
  produced it, so a dashboard can distinguish "sentiment 0.8" backed by 400
  documents from the same number backed by three.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Float, Interval, and_, cast, desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from pulseai.models import Document, Mention, Model, Sentiment, Source


@dataclass
class ModelStat:
    slug: str
    name: str
    company: str
    mentions: int
    documents: int
    sentiment: float
    positive_share: float
    negative_share: float
    #: None when the prior window holds no data at all — on a fresh install
    #: every model would otherwise read as +100% growth, which says "everything
    #: is exploding" when the truth is "we have no history yet".
    momentum: float | None


def _weight():
    """Confidence weight shared by every averaged metric."""
    return cast(Mention.confidence, Float) * cast(Sentiment.confidence, Float)


def _weighted_sentiment():
    """Weighted mean of compound sentiment, safe when all weights are zero.

    Low-confidence heuristic scores legitimately produce a zero weight sum; the
    NULLIF keeps that a 0.0 rather than a division error.
    """
    weight = _weight()
    return func.coalesce(
        func.sum(Sentiment.compound * weight) / func.nullif(func.sum(weight), 0.0), 0.0
    )


#: Minimum analyzer confidence for a document to be quoted as praise or a
#: complaint. Aggregates can absorb weak signal; a named example cannot.
_QUOTE_MIN_CONFIDENCE = 0.15


def _window(hours: int):
    return Document.published_at >= datetime.now(UTC) - timedelta(hours=hours)


async def model_leaderboard(
    session: AsyncSession, hours: int = 168, limit: int = 40
) -> list[ModelStat]:
    """Mentions, sentiment, and momentum per model over a trailing window."""
    current = (
        select(
            Model.slug,
            Model.name,
            Model.company,
            func.count(Mention.id).label("mentions"),
            func.count(func.distinct(Document.id)).label("documents"),
            _weighted_sentiment().label("sentiment"),
            func.sum(
                func.greatest(Sentiment.compound, 0.0)
            ).label("positive_mass"),
            func.sum(
                func.greatest(-Sentiment.compound, 0.0)
            ).label("negative_mass"),
        )
        .select_from(Mention)
        .join(Document, Document.id == Mention.document_id)
        .join(Model, Model.id == Mention.model_id)
        .join(
            Sentiment,
            and_(
                Sentiment.document_id == Mention.document_id,
                Sentiment.model_id == Mention.model_id,
            ),
            isouter=True,
        )
        .where(_window(hours))
        .group_by(Model.slug, Model.name, Model.company)
        .order_by(desc("mentions"))
        .limit(limit)
    )

    rows = (await session.execute(current)).all()
    prior = await _prior_mention_counts(session, hours)

    stats: list[ModelStat] = []
    for row in rows:
        positive = float(row.positive_mass or 0.0)
        negative = float(row.negative_mass or 0.0)
        mass = positive + negative
        previous = prior.get(row.slug, 0)
        stats.append(
            ModelStat(
                slug=row.slug,
                name=row.name,
                company=row.company,
                mentions=int(row.mentions),
                documents=int(row.documents),
                sentiment=round(float(row.sentiment or 0.0), 4),
                positive_share=round(positive / mass, 4) if mass else 0.0,
                negative_share=round(negative / mass, 4) if mass else 0.0,
                momentum=_momentum(int(row.mentions), previous),
            )
        )
    return stats


async def _prior_mention_counts(session: AsyncSession, hours: int) -> dict[str, int]:
    """Mention counts for the equally-sized window immediately before this one."""
    now = datetime.now(UTC)
    start = now - timedelta(hours=hours * 2)
    end = now - timedelta(hours=hours)

    rows = await session.execute(
        select(Model.slug, func.count(Mention.id))
        .select_from(Mention)
        .join(Document, Document.id == Mention.document_id)
        .join(Model, Model.id == Mention.model_id)
        .where(and_(Document.published_at >= start, Document.published_at < end))
        .group_by(Model.slug)
    )
    return {slug: int(count) for slug, count in rows.all()}


def _momentum(current: int, previous: int) -> float | None:
    """Growth versus the previous window, or None when it is not computable.

    Growth from zero is infinite, which is true and useless — and on a young
    corpus it would mark every model as +100%, making the column pure noise
    exactly when it is least informative. Reporting nothing is more honest than
    reporting a number that only means "we have no baseline".

    Where a baseline does exist, the ratio is capped at ±1 so one explosive
    model cannot flatten the rest of the column.
    """
    if previous == 0:
        return None
    return round(max(-1.0, min(1.0, (current - previous) / previous)), 4)


async def sentiment_timeseries(
    session: AsyncSession,
    slug: str | None = None,
    hours: int = 168,
    bucket_hours: int = 24,
) -> list[dict]:
    """Confidence-weighted sentiment per time bucket, optionally for one model."""
    # date_bin needs a fixed origin so buckets are stable across requests rather
    # than sliding with "now" — otherwise the same document lands in a different
    # bucket on every poll and the chart jitters.
    bucket = func.date_bin(
        cast(literal(f"{bucket_hours} hours"), Interval),
        Document.published_at,
        cast(literal("2000-01-01 00:00:00+00"), DateTime(timezone=True)),
    ).label("bucket")

    query = (
        select(
            bucket,
            func.count(Mention.id).label("mentions"),
            _weighted_sentiment().label("sentiment"),
        )
        .select_from(Mention)
        .join(Document, Document.id == Mention.document_id)
        .join(Model, Model.id == Mention.model_id)
        .join(
            Sentiment,
            and_(
                Sentiment.document_id == Mention.document_id,
                Sentiment.model_id == Mention.model_id,
            ),
            isouter=True,
        )
        .where(_window(hours))
        .group_by("bucket")
        .order_by("bucket")
    )
    if slug:
        query = query.where(Model.slug == slug)

    rows = (await session.execute(query)).all()
    return [
        {
            "bucket": row.bucket.isoformat(),
            "mentions": int(row.mentions),
            "sentiment": round(float(row.sentiment or 0.0), 4),
        }
        for row in rows
    ]


async def source_breakdown(session: AsyncSession, hours: int = 168) -> list[dict]:
    rows = await session.execute(
        select(
            Source.name,
            func.count(func.distinct(Document.id)).label("documents"),
            func.count(Mention.id).label("mentions"),
        )
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
        .join(Mention, Mention.document_id == Document.id, isouter=True)
        .where(_window(hours))
        .group_by(Source.name)
        .order_by(desc("documents"))
    )
    return [
        {"source": name, "documents": int(documents), "mentions": int(mentions)}
        for name, documents, mentions in rows.all()
    ]


async def model_documents(
    session: AsyncSession,
    slug: str,
    hours: int = 168,
    limit: int = 25,
    polarity: str = "all",
) -> list[dict]:
    """Representative documents for a model, optionally only praise or complaints."""
    query = (
        select(
            Document.title,
            Document.url,
            Document.author,
            Document.published_at,
            Document.score,
            Source.name.label("source"),
            Sentiment.compound,
            Mention.confidence,
            func.substr(Document.content, 1, 400).label("excerpt"),
        )
        .select_from(Mention)
        .join(Document, Document.id == Mention.document_id)
        .join(Source, Source.id == Document.source_id)
        .join(Model, Model.id == Mention.model_id)
        .join(
            Sentiment,
            and_(
                Sentiment.document_id == Mention.document_id,
                Sentiment.model_id == Mention.model_id,
            ),
            isouter=True,
        )
        .where(and_(Model.slug == slug, _window(hours)))
        .limit(limit)
    )

    # Praise and complaint lists are quotes shown to a reader, so they need a
    # higher bar than the aggregate: a barely-signed score on a document with
    # one weak signal word is not somebody complaining. Filtering on confidence
    # as well as sign keeps titles like "Add Claude Code GitHub Workflow" out of
    # a list captioned "top complaints".
    if polarity == "positive":
        query = query.where(
            and_(Sentiment.compound > 0.08, Sentiment.confidence >= _QUOTE_MIN_CONFIDENCE)
        ).order_by(desc(Sentiment.compound))
    elif polarity == "negative":
        query = query.where(
            and_(Sentiment.compound < -0.08, Sentiment.confidence >= _QUOTE_MIN_CONFIDENCE)
        ).order_by(Sentiment.compound)
    else:
        query = query.order_by(desc(Document.published_at))

    rows = (await session.execute(query)).all()
    return [
        {
            "title": row.title,
            "url": row.url,
            "author": row.author,
            "published_at": row.published_at.isoformat(),
            "score": row.score,
            "source": row.source,
            "sentiment": round(float(row.compound or 0.0), 4),
            "confidence": round(float(row.confidence or 0.0), 4),
            "excerpt": (row.excerpt or "").strip(),
        }
        for row in rows
    ]


async def corpus_summary(session: AsyncSession) -> dict:
    """Totals for the header. Deliberately includes what is *not* yet analysed."""
    documents = int(
        (await session.execute(select(func.count()).select_from(Document))).scalar_one()
    )
    enriched = int(
        (
            await session.execute(
                select(func.count()).select_from(Document).where(
                    Document.enriched_at.is_not(None)
                )
            )
        ).scalar_one()
    )
    mentions = int(
        (await session.execute(select(func.count()).select_from(Mention))).scalar_one()
    )
    models_tracked = int(
        (
            await session.execute(
                select(func.count()).select_from(Model).where(Model.active.is_(True))
            )
        ).scalar_one()
    )
    newest = (
        await session.execute(select(func.max(Document.published_at)))
    ).scalar_one()

    return {
        "documents": documents,
        "enriched": enriched,
        "pending": documents - enriched,
        "mentions": mentions,
        "models_tracked": models_tracked,
        "latest_document": newest.isoformat() if newest else None,
    }


async def compare_models(
    session: AsyncSession, slugs: list[str], hours: int = 168
) -> list[dict]:
    stats = {stat.slug: stat for stat in await model_leaderboard(session, hours, limit=200)}
    output = []
    for slug in slugs:
        stat = stats.get(slug)
        output.append(
            {
                "slug": slug,
                "name": stat.name if stat else slug,
                "company": stat.company if stat else "",
                "mentions": stat.mentions if stat else 0,
                "documents": stat.documents if stat else 0,
                "sentiment": stat.sentiment if stat else 0.0,
                "positive_share": stat.positive_share if stat else 0.0,
                "negative_share": stat.negative_share if stat else 0.0,
                "momentum": stat.momentum if stat else None,
            }
        )
    return output
