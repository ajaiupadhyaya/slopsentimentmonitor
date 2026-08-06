"""News and vendor blogs over RSS.

Free, unauthenticated, and the only source that reliably carries first-party
release announcements — which is what makes "sentiment before/after a release"
answerable later.

Vendor blogs are kept in the same list as press deliberately. They are not
neutral, but their publication timestamps are the ground truth for when a
release actually landed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import feedparser
import structlog

from pulseai.collectors.base import HttpCollector, RawDocument
from pulseai.text import strip_html

log = structlog.get_logger(__name__)

FEEDS: dict[str, str] = {
    # Press
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "VentureBeat": "https://venturebeat.com/category/ai/feed/",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "Hacker News Frontpage": "https://hnrss.org/frontpage",
    # First-party. Verified reachable 2026-08-06; blogs.microsoft.com/ai and
    # ai.meta.com/blog/rss both 4xx'd and were replaced with live equivalents.
    # Anthropic publishes no RSS feed — its releases arrive via press coverage.
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Microsoft": "https://blogs.microsoft.com/feed/",
    "Meta Engineering": "https://engineering.fb.com/feed/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
}


class RSSCollector(HttpCollector):
    name = "news"
    type = "news"

    def __init__(self, *args: Any, feeds: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.feeds = feeds if feeds is not None else FEEDS

    async def collect(self, limit: int = 300) -> AsyncIterator[RawDocument]:
        per_feed = max(5, limit // max(len(self.feeds), 1))
        emitted = 0

        for outlet, url in self.feeds.items():
            if emitted >= limit:
                return
            try:
                body = await self.get_text(url)
            except Exception as exc:
                log.warning("rss.fetch_failed", outlet=outlet, url=url, error=str(exc))
                continue

            # feedparser is synchronous and CPU-bound on large feeds; keep it
            # off the event loop so concurrent collectors are not stalled.
            parsed = await asyncio.to_thread(feedparser.parse, body)
            for entry in parsed.entries[:per_feed]:
                doc = self._to_document(outlet, entry)
                if doc is None:
                    continue
                emitted += 1
                yield doc
                if emitted >= limit:
                    return

    def _to_document(self, outlet: str, entry: Any) -> RawDocument | None:
        link = entry.get("link")
        if not link:
            return None

        summary = entry.get("summary", "")
        if contents := entry.get("content"):
            summary = max((c.get("value", "") for c in contents), key=len, default=summary)

        return RawDocument(
            source=self.name,
            external_id=entry.get("id") or link,
            published_at=_entry_time(entry),
            title=entry.get("title"),
            content=strip_html(summary)[:20000],
            url=link,
            author=entry.get("author") or outlet,
            raw={"outlet": outlet, "tags": [t.get("term") for t in entry.get("tags", [])]},
        )


def _entry_time(entry: Any) -> datetime:
    """Feeds disagree about which time field they populate; some omit all of them."""
    import calendar

    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        if value := entry.get(key):
            return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
    return datetime.now(UTC)


