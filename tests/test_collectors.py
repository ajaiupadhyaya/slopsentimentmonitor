"""Collector tests against recorded payloads.

Payload shapes are trimmed from real responses captured on 2026-08-06. No test
here touches the network — the one live check is in `test_live.py`, marked so it
is deselected by default.
"""

from __future__ import annotations

from datetime import UTC

import httpx
import pytest
import respx

from pulseai.collectors.github import GitHubCollector
from pulseai.collectors.hackernews import HackerNewsCollector
from pulseai.collectors.reddit import RedditCollector
from pulseai.collectors.rss import RSSCollector
from pulseai.config import Settings

HN_PAYLOAD = {
    "hits": [
        {
            "objectID": "44112233",
            "created_at_i": 1786000000,
            "title": None,
            "story_title": "Ask HN: Which model for coding?",
            # Escaped markup is how HN actually stores comments; a strip-then-
            # unescape pass would leak a literal <b> into the analyzed text.
            "comment_text": (
                "I switched to &lt;b&gt;Claude&lt;/b&gt; last month.<p>It&#x27;s faster."
            ),
            "author": "someone",
            "points": None,
            "num_comments": None,
            "_tags": ["comment"],
        },
        {
            "objectID": "44112299",
            "created_at_i": 1786000500,
            "title": "Show HN: A local LLM router",
            "story_text": "Routes between ollama and hosted models.",
            "author": "builder",
            "points": 42,
            "num_comments": 7,
            "url": "https://example.test/router",
            "_tags": ["story"],
        },
    ]
}

GITHUB_PAYLOAD = {
    "items": [
        {
            "node_id": "I_kwDO123",
            "created_at": "2026-08-05T10:00:00Z",
            "title": "[BUG] rate limits hit immediately",
            "body": "Every request 429s after the update.",
            "html_url": "https://github.com/acme/tool/issues/12",
            "repository_url": "https://api.github.com/repos/acme/tool",
            "user": {"login": "reporter"},
            "reactions": {"total_count": 5},
            "comments": 3,
            "state": "open",
            "labels": [{"name": "bug"}],
        }
    ]
}

REDDIT_PAYLOAD = {
    "data": {
        "children": [
            {
                "data": {
                    "name": "t3_abc123",
                    "created_utc": 1786000000.0,
                    "title": "Gemini vs Claude for long context",
                    "selftext": "Been testing both this week.",
                    "permalink": "/r/LocalLLaMA/comments/abc123/",
                    "author": "tester",
                    "score": 88,
                    "ups": 88,
                    "num_comments": 24,
                    "link_flair_text": "Discussion",
                    "upvote_ratio": 0.94,
                }
            }
        ]
    }
}

RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Test Outlet</title>
  <item>
    <title>OpenAI ships a new model</title>
    <link>https://example.test/story</link>
    <guid>https://example.test/story</guid>
    <pubDate>Tue, 05 Aug 2026 12:00:00 GMT</pubDate>
    <description>&lt;p&gt;The company &lt;b&gt;announced&lt;/b&gt; it today.&lt;/p&gt;</description>
  </item>
</channel></rss>
"""


async def _drain(collector, limit: int = 50):
    async with collector:
        return [doc async for doc in collector.collect(limit)]


# ---------------------------------------------------------------------------
# Hacker News
# ---------------------------------------------------------------------------


@respx.mock
async def test_hackernews_parses_stories_and_comments() -> None:
    respx.get(url__startswith="https://hn.algolia.com").mock(
        return_value=httpx.Response(200, json=HN_PAYLOAD)
    )

    documents = await _drain(HackerNewsCollector(Settings(http_backoff_factor=0)), limit=2)

    assert len(documents) == 2
    comment = next(d for d in documents if d.external_id == "44112233")
    assert comment.source == "hackernews"
    assert comment.published_at.tzinfo is UTC
    assert comment.url == "https://news.ycombinator.com/item?id=44112233"


@respx.mock
async def test_hackernews_strips_stored_html_and_entities() -> None:
    """Algolia returns HN's stored markup, which would otherwise reach the analyzer."""
    respx.get(url__startswith="https://hn.algolia.com").mock(
        return_value=httpx.Response(200, json=HN_PAYLOAD)
    )

    documents = await _drain(HackerNewsCollector(Settings(http_backoff_factor=0)), limit=2)
    comment = next(d for d in documents if d.external_id == "44112233")

    assert "<b>" not in comment.content
    assert "&#x27;" not in comment.content
    assert "Claude" in comment.content
    assert "It's faster" in comment.content


@respx.mock
async def test_hackernews_deduplicates_across_queries() -> None:
    """The same item legitimately matches several of the search terms."""
    respx.get(url__startswith="https://hn.algolia.com").mock(
        return_value=httpx.Response(200, json=HN_PAYLOAD)
    )

    documents = await _drain(HackerNewsCollector(Settings(http_backoff_factor=0)), limit=50)
    ids = [d.external_id for d in documents]
    assert len(ids) == len(set(ids))


@respx.mock
async def test_hackernews_survives_a_failing_query() -> None:
    """One bad search term must not cost the whole run."""
    respx.get(url__startswith="https://hn.algolia.com").mock(
        return_value=httpx.Response(500, json={})
    )

    assert await _drain(HackerNewsCollector(Settings(http_backoff_factor=0)), limit=5) == []


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


@respx.mock
async def test_github_parses_issues() -> None:
    respx.get(url__startswith="https://api.github.com").mock(
        return_value=httpx.Response(200, json=GITHUB_PAYLOAD)
    )

    collector = GitHubCollector(Settings(http_backoff_factor=0), since_hours=72)
    collector._SEARCH_INTERVAL_SECONDS = 0  # keep the test fast
    documents = await _drain(collector, limit=1)

    assert len(documents) == 1
    doc = documents[0]
    assert doc.source == "github"
    assert doc.raw["repo"] == "acme/tool"
    assert doc.raw["is_pull_request"] is False
    assert doc.author == "reporter"
    assert doc.score == 5


@respx.mock
async def test_github_sends_the_token_when_present() -> None:
    route = respx.get(url__startswith="https://api.github.com").mock(
        return_value=httpx.Response(200, json=GITHUB_PAYLOAD)
    )

    settings = Settings(github_token="ghp_test", http_backoff_factor=0)
    collector = GitHubCollector(settings, since_hours=72)
    collector._SEARCH_INTERVAL_SECONDS = 0
    await _drain(collector, limit=1)

    assert route.calls[0].request.headers["Authorization"] == "Bearer ghp_test"


def test_github_reports_the_unauthenticated_rate_limit() -> None:
    available, reason = GitHubCollector(Settings(http_backoff_factor=0)).available()
    assert available
    assert "10 search requests" in reason


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------


def test_reddit_is_unavailable_without_credentials() -> None:
    available, reason = RedditCollector(Settings(http_backoff_factor=0)).available()
    assert not available
    assert "PULSEAI_REDDIT_CLIENT_ID" in reason


def test_reddit_is_available_with_credentials() -> None:
    settings = Settings(reddit_client_id="id", reddit_client_secret="secret", http_backoff_factor=0)
    available, _ = RedditCollector(settings).available()
    assert available


async def test_reddit_yields_nothing_when_dormant() -> None:
    """Skipping must be silent and empty, never an exception."""
    assert await _drain(RedditCollector(Settings(http_backoff_factor=0)), limit=10) == []


@respx.mock
async def test_reddit_authenticates_then_parses_listings() -> None:
    respx.post("https://www.reddit.com/api/v1/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    respx.get(url__startswith="https://oauth.reddit.com").mock(
        return_value=httpx.Response(200, json=REDDIT_PAYLOAD)
    )

    settings = Settings(reddit_client_id="id", reddit_client_secret="secret", http_backoff_factor=0)
    collector = RedditCollector(settings, subreddits=("LocalLLaMA",))
    collector._REQUEST_INTERVAL_SECONDS = 0
    documents = await _drain(collector, limit=5)

    assert len(documents) == 1
    doc = documents[0]
    assert doc.external_id == "t3_abc123"
    assert doc.raw["subreddit"] == "LocalLLaMA"
    assert doc.score == 88
    assert doc.url.startswith("https://reddit.com/r/LocalLLaMA")


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------


@respx.mock
async def test_rss_parses_and_strips_markup() -> None:
    respx.get("https://feed.test/rss").mock(return_value=httpx.Response(200, text=RSS_FEED))

    collector = RSSCollector(Settings(http_backoff_factor=0), feeds={"Test Outlet": "https://feed.test/rss"})
    documents = await _drain(collector, limit=5)

    assert len(documents) == 1
    doc = documents[0]
    assert doc.title == "OpenAI ships a new model"
    assert "<b>" not in doc.content
    assert "announced" in doc.content
    assert doc.raw["outlet"] == "Test Outlet"


@respx.mock
async def test_rss_continues_past_a_dead_feed() -> None:
    """Two of the shipped feeds 4xx'd in production; the rest must still land."""
    respx.get("https://dead.test/rss").mock(return_value=httpx.Response(410))
    respx.get("https://live.test/rss").mock(return_value=httpx.Response(200, text=RSS_FEED))

    collector = RSSCollector(
        Settings(http_backoff_factor=0),
        feeds={"Dead": "https://dead.test/rss", "Live": "https://live.test/rss"},
    )
    documents = await _drain(collector, limit=5)

    assert len(documents) == 1
    assert documents[0].raw["outlet"] == "Live"


@respx.mock
async def test_rss_falls_back_when_a_feed_omits_dates() -> None:
    feed = RSS_FEED.replace("<pubDate>Tue, 05 Aug 2026 12:00:00 GMT</pubDate>", "")
    respx.get("https://feed.test/rss").mock(return_value=httpx.Response(200, text=feed))

    collector = RSSCollector(Settings(http_backoff_factor=0), feeds={"Test": "https://feed.test/rss"})
    documents = await _drain(collector, limit=5)

    assert documents[0].published_at is not None


# ---------------------------------------------------------------------------
# Shared HTTP behaviour
# ---------------------------------------------------------------------------


@respx.mock
async def test_transient_server_errors_are_retried() -> None:
    route = respx.get("https://feed.test/rss").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, text=RSS_FEED)]
    )

    collector = RSSCollector(Settings(http_max_retries=3, http_backoff_factor=0), feeds={"T": "https://feed.test/rss"})
    documents = await _drain(collector, limit=5)

    assert route.call_count == 2
    assert len(documents) == 1


@respx.mock
async def test_client_errors_are_not_retried() -> None:
    """Retrying a 404 or a bad token wastes the rate limit and never succeeds."""
    route = respx.get("https://feed.test/rss").mock(return_value=httpx.Response(404))

    collector = RSSCollector(Settings(http_max_retries=3, http_backoff_factor=0), feeds={"T": "https://feed.test/rss"})
    await _drain(collector, limit=5)

    assert route.call_count == 1


def test_client_use_outside_context_manager_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="async context manager"):
        _ = RSSCollector(Settings(http_backoff_factor=0)).client
