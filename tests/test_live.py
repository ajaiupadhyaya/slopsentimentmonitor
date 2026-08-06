"""Live smoke checks against the real internet.

Deselected by default (`addopts = -m 'not live'`). Run explicitly with:

    uv run pytest -m live

These exist to catch the failure the mocked tests structurally cannot: an
upstream API changing its response shape. Two of the shipped RSS feeds had
already died this way.
"""

from __future__ import annotations

import pytest

from pulseai.collectors.hackernews import HackerNewsCollector
from pulseai.collectors.rss import FEEDS, RSSCollector
from pulseai.config import Settings

pytestmark = pytest.mark.live


async def test_hackernews_returns_usable_documents() -> None:
    collector = HackerNewsCollector(Settings(), since_hours=72)
    async with collector:
        documents = [doc async for doc in collector.collect(10)]

    assert documents, "Algolia returned nothing — check the API shape"
    for doc in documents:
        assert doc.external_id
        assert doc.published_at.tzinfo is not None
        assert doc.title or doc.content
        assert "<p>" not in doc.content


async def test_every_shipped_rss_feed_is_reachable() -> None:
    """Feeds rot. This names the dead one instead of silently collecting less."""
    collector = RSSCollector(Settings())
    dead: list[str] = []

    async with collector:
        for outlet, url in FEEDS.items():
            try:
                body = await collector.get_text(url)
                if "<rss" not in body and "<feed" not in body:
                    dead.append(f"{outlet} (not a feed)")
            except Exception as exc:
                dead.append(f"{outlet} ({type(exc).__name__})")

    assert not dead, f"unreachable feeds: {', '.join(dead)}"


async def test_detection_finds_models_in_real_hacker_news_text() -> None:
    """End-to-end reality check: real prose, real matches."""
    from pulseai.pipeline.clean import clean
    from pulseai.pipeline.detect import ModelDetector
    from pulseai.registry import MODELS

    detector = ModelDetector.from_specs(MODELS)
    collector = HackerNewsCollector(Settings(), since_hours=72)

    async with collector:
        documents = [doc async for doc in collector.collect(40)]

    matched = 0
    for doc in documents:
        text = clean(f"{doc.title or ''}\n{doc.content}").text
        if detector.detect(text):
            matched += 1

    assert matched > 0, "no model detected in 40 live Hacker News documents"
