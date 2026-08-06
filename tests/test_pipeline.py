"""End-to-end enrichment against a real database.

Covers the properties that only appear once the stages are composed: that
re-running enrichment is safe, that the catalog drives detection at runtime, and
that a comparison document really does score each model separately.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from pulseai.models import Document, Mention, Model, Sentiment, Source
from pulseai.pipeline.analyze import HeuristicAnalyzer
from pulseai.pipeline.run import _enrich_one, build_detector
from pulseai.registry import MODELS

pytestmark = pytest.mark.db


async def _seed_models(session) -> dict[str, int]:
    """Insert the real catalog so detection behaves as it does in production."""
    from dataclasses import asdict

    for spec in MODELS:
        session.add(
            Model(
                slug=spec.slug,
                name=spec.name,
                company=spec.company,
                website=spec.website,
                aliases=[asdict(alias) for alias in spec.all_aliases()],
                active=True,
            )
        )
    await session.flush()
    rows = (await session.execute(select(Model.slug, Model.id))).all()
    return {slug: model_id for slug, model_id in rows}


async def _add_document(session, text: str, title: str = "t", author: str = "human") -> Document:
    source = Source(name="test", type="forum", priority=1, enabled=True)
    session.add(source)
    await session.flush()

    document = Document(
        source_id=source.id,
        external_id="ext-1",
        title=title,
        content=text,
        published_at=datetime.now(UTC),
        author=author,
    )
    session.add(document)
    await session.flush()
    return document


async def _enrich(session, document: Document, model_ids: dict[str, int]):
    detector = await build_detector(session)
    return await _enrich_one(session, document, detector, HeuristicAnalyzer(), model_ids)


async def test_full_enrichment_writes_mentions_and_sentiment(session) -> None:
    model_ids = await _seed_models(session)
    document = await _add_document(
        session, "ChatGPT has been excellent for drafting, really impressive lately."
    )

    mentions, sentiments = await _enrich(session, document, model_ids)
    await session.flush()

    assert mentions == 1
    assert sentiments == 1

    stored = (
        await session.execute(
            select(Mention).join(Model).where(Model.slug == "chatgpt")
        )
    ).scalars().all()
    assert len(stored) == 1
    assert document.enriched_at is not None


async def test_detector_is_built_from_the_database(session) -> None:
    """A model added at runtime must be detected without a code change."""
    session.add(
        Model(
            slug="zephyr-x",
            name="Zephyr X",
            company="Fictional Labs",
            aliases=[{"text": "Zephyr X", "case_sensitive": False,
                      "requires_context": False, "weight": 1.0, "blocked_next": []}],
            active=True,
        )
    )
    await session.flush()

    detector = await build_detector(session)
    assert "zephyr-x" in {m.slug for m in detector.detect("Zephyr X is surprisingly good")}


async def test_inactive_models_are_not_detected(session) -> None:
    session.add(
        Model(
            slug="retired",
            name="Retired Model",
            company="Old Co",
            aliases=[{"text": "Retired Model", "case_sensitive": False,
                      "requires_context": False, "weight": 1.0, "blocked_next": []}],
            active=False,
        )
    )
    await session.flush()

    detector = await build_detector(session)
    assert detector.detect("Retired Model was great") == []


async def test_enrichment_is_idempotent(session) -> None:
    """Re-running after an analyzer improvement must replace, not accumulate."""
    model_ids = await _seed_models(session)
    document = await _add_document(session, "Claude is genuinely excellent at refactoring.")

    await _enrich(session, document, model_ids)
    await session.flush()
    await _enrich(session, document, model_ids)
    await session.flush()

    mentions = (
        await session.execute(select(Mention).where(Mention.document_id == document.id))
    ).scalars().all()
    sentiments = (
        await session.execute(select(Sentiment).where(Sentiment.document_id == document.id))
    ).scalars().all()

    assert len(mentions) == 1
    assert len(sentiments) == 1


async def test_comparison_document_scores_each_model_independently(session) -> None:
    """The reason sentiment is keyed per (document, model) rather than per document."""
    model_ids = await _seed_models(session)
    document = await _add_document(
        session,
        "ChatGPT has been excellent here, genuinely impressive and reliable for our team. "
        + ("Filler sentence to separate the two subjects. " * 12)
        + "Gemini by contrast keeps hallucinating and the errors are frustrating and useless.",
    )

    await _enrich(session, document, model_ids)
    await session.flush()

    rows = (
        await session.execute(
            select(Model.slug, Sentiment.compound)
            .join(Sentiment, Sentiment.model_id == Model.id)
            .where(Sentiment.document_id == document.id)
        )
    ).all()
    scores = {slug: compound for slug, compound in rows}

    assert scores["chatgpt"] > 0
    assert scores["gemini"] < 0


async def test_attribution_trailer_produces_no_mentions(session) -> None:
    """The 18.6% problem, asserted end to end."""
    model_ids = await _seed_models(session)
    document = await _add_document(
        session,
        "Bumps the eslint rule and fixes 12 call sites.\n\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>",
        title="Enable eslint max-depth rule",
    )

    mentions, _ = await _enrich(session, document, model_ids)
    assert mentions == 0


async def test_bot_authored_documents_are_skipped(session) -> None:
    model_ids = await _seed_models(session)
    document = await _add_document(
        session,
        "Bump anthropic from 0.40.0 to 0.41.0. Claude SDK release notes attached.",
        title="chore(deps): bump anthropic",
        author="dependabot[bot]",
    )

    mentions, _ = await _enrich(session, document, model_ids)
    assert mentions == 0


async def test_document_with_no_models_is_still_marked_enriched(session) -> None:
    """Otherwise it is re-analysed forever and the pending count never drains."""
    model_ids = await _seed_models(session)
    document = await _add_document(session, "Discussion about Postgres index bloat.")

    mentions, _ = await _enrich(session, document, model_ids)
    assert mentions == 0
    assert document.enriched_at is not None
