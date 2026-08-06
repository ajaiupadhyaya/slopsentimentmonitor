"""Aggregate queries, against a real Postgres.

Weighted averages are the kind of SQL that returns a plausible number when it is
wrong, so these assert arithmetic rather than shape.
"""

from __future__ import annotations

import pytest

from pulseai import analytics
from pulseai.analytics import _momentum

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# Momentum — pure, no database
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (150, 100, 0.5),
        (50, 100, -0.5),
        (100, 100, 0.0),
        (1000, 10, 1.0),   # growth capped; the raw ratio is +99
        (0, 1000, -1.0),   # a total collapse is the natural floor, not a cap
    ],
)
def test_momentum_ratio(current: int, previous: int, expected: float) -> None:
    assert _momentum(current, previous) == pytest.approx(expected)


def test_momentum_is_none_without_a_baseline() -> None:
    """Growth from zero is not 100% — it is unknown, and must not be reported."""
    assert _momentum(50, 0) is None
    assert _momentum(0, 0) is None


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


async def test_leaderboard_counts_and_averages(corpus) -> None:
    await corpus.add("alpha", compound=0.6)
    await corpus.add("alpha", compound=0.2)
    await corpus.add("beta", compound=-0.4)

    stats = await analytics.model_leaderboard(corpus.session, hours=168)
    by_slug = {s.slug: s for s in stats}

    assert by_slug["alpha"].mentions == 2
    assert by_slug["alpha"].sentiment == pytest.approx(0.4)
    assert by_slug["beta"].mentions == 1
    assert by_slug["beta"].sentiment == pytest.approx(-0.4)


async def test_leaderboard_sorts_by_volume(corpus) -> None:
    for _ in range(3):
        await corpus.add("loud", compound=-0.9)
    await corpus.add("quiet", compound=0.9)

    stats = await analytics.model_leaderboard(corpus.session, hours=168)
    assert stats[0].slug == "loud"


async def test_low_confidence_moves_the_average_less(corpus) -> None:
    """The core weighting rule: a hesitant read should not outvote a certain one."""
    await corpus.add("alpha", compound=1.0, sentiment_confidence=1.0)
    await corpus.add("alpha", compound=-1.0, sentiment_confidence=0.1)

    stats = await analytics.model_leaderboard(corpus.session, hours=168)
    sentiment = next(s.slug == "alpha" and s.sentiment for s in stats if s.slug == "alpha")

    assert sentiment > 0.5  # an unweighted mean would land at 0.0


async def test_mention_confidence_also_weights(corpus) -> None:
    await corpus.add("alpha", compound=1.0, mention_confidence=1.0)
    await corpus.add("alpha", compound=-1.0, mention_confidence=0.1)

    stats = await analytics.model_leaderboard(corpus.session, hours=168)
    assert next(s.sentiment for s in stats if s.slug == "alpha") > 0.5


async def test_zero_weight_does_not_divide_by_zero(corpus) -> None:
    """Every heuristic score on a neutral document has zero confidence."""
    await corpus.add("alpha", compound=0.0, sentiment_confidence=0.0, mention_confidence=0.0)

    stats = await analytics.model_leaderboard(corpus.session, hours=168)
    assert next(s.sentiment for s in stats if s.slug == "alpha") == 0.0


async def test_window_excludes_older_documents(corpus) -> None:
    await corpus.add("alpha", compound=0.5, hours_ago=1)
    await corpus.add("alpha", compound=0.5, hours_ago=400)

    recent = await analytics.model_leaderboard(corpus.session, hours=24)
    assert next(s.mentions for s in recent if s.slug == "alpha") == 1

    wide = await analytics.model_leaderboard(corpus.session, hours=720)
    assert next(s.mentions for s in wide if s.slug == "alpha") == 2


async def test_momentum_compares_against_the_preceding_window(corpus) -> None:
    # Window is 24h, so the baseline window is 24-48h ago.
    for _ in range(4):
        await corpus.add("alpha", compound=0.1, hours_ago=2)
    for _ in range(2):
        await corpus.add("alpha", compound=0.1, hours_ago=30)

    stats = await analytics.model_leaderboard(corpus.session, hours=24)
    assert next(s.momentum for s in stats if s.slug == "alpha") == pytest.approx(1.0)


async def test_momentum_is_none_for_a_model_with_no_prior_mentions(corpus) -> None:
    """One old document from another model must not fabricate a baseline."""
    await corpus.add("newcomer", compound=0.1, hours_ago=2)
    await corpus.add("veteran", compound=0.1, hours_ago=30)

    stats = await analytics.model_leaderboard(corpus.session, hours=24)
    assert next(s.momentum for s in stats if s.slug == "newcomer") is None


async def test_positive_and_negative_shares_sum_to_one(corpus) -> None:
    await corpus.add("alpha", compound=0.6)
    await corpus.add("alpha", compound=-0.2)

    stats = await analytics.model_leaderboard(corpus.session, hours=168)
    stat = next(s for s in stats if s.slug == "alpha")
    assert stat.positive_share + stat.negative_share == pytest.approx(1.0)
    assert stat.positive_share == pytest.approx(0.75)


async def test_empty_corpus_returns_no_rows(corpus) -> None:
    assert await analytics.model_leaderboard(corpus.session, hours=168) == []


# ---------------------------------------------------------------------------
# Timeseries
# ---------------------------------------------------------------------------


async def test_timeseries_buckets_by_day(corpus) -> None:
    await corpus.add("alpha", compound=0.5, hours_ago=2)
    await corpus.add("alpha", compound=0.5, hours_ago=3)
    await corpus.add("alpha", compound=-0.5, hours_ago=40)

    series = await analytics.sentiment_timeseries(
        corpus.session, "alpha", hours=168, bucket_hours=24
    )
    assert len(series) == 2
    assert sum(point["mentions"] for point in series) == 3


async def test_timeseries_is_ordered_oldest_first(corpus) -> None:
    await corpus.add("alpha", compound=0.1, hours_ago=2)
    await corpus.add("alpha", compound=0.1, hours_ago=50)
    await corpus.add("alpha", compound=0.1, hours_ago=100)

    series = await analytics.sentiment_timeseries(corpus.session, "alpha", hours=168)
    buckets = [point["bucket"] for point in series]
    assert buckets == sorted(buckets)


async def test_timeseries_filters_by_model(corpus) -> None:
    await corpus.add("alpha", compound=0.5)
    await corpus.add("beta", compound=-0.5)

    series = await analytics.sentiment_timeseries(corpus.session, "alpha", hours=168)
    assert sum(point["mentions"] for point in series) == 1


# ---------------------------------------------------------------------------
# Quoted documents
# ---------------------------------------------------------------------------


async def test_praise_and_complaints_are_separated(corpus) -> None:
    await corpus.add("alpha", compound=0.7, title="loved it")
    await corpus.add("alpha", compound=-0.7, title="hated it")

    praise = await analytics.model_documents(corpus.session, "alpha", polarity="positive")
    complaints = await analytics.model_documents(corpus.session, "alpha", polarity="negative")

    assert [d["title"] for d in praise] == ["loved it"]
    assert [d["title"] for d in complaints] == ["hated it"]


async def test_low_confidence_documents_are_not_quoted(corpus) -> None:
    """Aggregates may absorb weak signal; a named example may not."""
    await corpus.add("alpha", compound=-0.5, sentiment_confidence=0.02, title="barely negative")

    complaints = await analytics.model_documents(corpus.session, "alpha", polarity="negative")
    assert complaints == []


async def test_complaints_are_ordered_most_negative_first(corpus) -> None:
    await corpus.add("alpha", compound=-0.2, title="mild")
    await corpus.add("alpha", compound=-0.9, title="severe")

    complaints = await analytics.model_documents(corpus.session, "alpha", polarity="negative")
    assert [d["title"] for d in complaints] == ["severe", "mild"]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


async def test_corpus_summary_reports_pending_work(corpus) -> None:
    await corpus.add("alpha", compound=0.5)

    summary = await analytics.corpus_summary(corpus.session)
    assert summary["documents"] == 1
    assert summary["mentions"] == 1
    # add() does not set enriched_at, so the document reads as pending.
    assert summary["pending"] == 1
    assert summary["latest_document"] is not None


async def test_source_breakdown_counts_documents_and_mentions(corpus) -> None:
    await corpus.add("alpha", compound=0.5)
    await corpus.add("beta", compound=0.5)

    sources = await analytics.source_breakdown(corpus.session, hours=168)
    assert sources[0]["source"] == "test"
    assert sources[0]["documents"] == 2
    assert sources[0]["mentions"] == 2
