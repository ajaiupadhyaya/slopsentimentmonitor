"""Hacker News via the Algolia search API.

Chosen over the official Firebase API because Algolia supports full-text query
plus date filtering, which means we can pull only documents that already mention
an LLM instead of crawling everything and discarding 99% of it.

No authentication, no rate limit worth worrying about.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from pulseai.collectors.base import HttpCollector, RawDocument
from pulseai.text import strip_html

log = structlog.get_logger(__name__)

API = "https://hn.algolia.com/api/v1/search_by_date"

#: Broad enough to catch discussion the narrow model aliases would miss, narrow
#: enough that detection still has real work to do. Detection decides which
#: model a document is about; these queries only decide what gets fetched.
QUERIES: tuple[str, ...] = (
    "ChatGPT", "OpenAI", "Claude", "Anthropic", "Gemini", "LLM",
    "GPT-5", "Grok", "DeepSeek", "Llama", "Mistral", "Copilot",
    "Perplexity", "Qwen", "ollama", "local model",
)


class HackerNewsCollector(HttpCollector):
    name = "hackernews"
    type = "forum"

    def __init__(self, *args: Any, since_hours: int = 72, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.since_hours = since_hours

    async def collect(self, limit: int = 500) -> AsyncIterator[RawDocument]:
        cutoff = int((datetime.now(UTC) - timedelta(hours=self.since_hours)).timestamp())
        per_query = max(10, limit // len(QUERIES))
        seen: set[str] = set()
        emitted = 0

        for query in QUERIES:
            if emitted >= limit:
                return
            for tag in ("story", "comment"):
                try:
                    payload = await self.get_json(
                        API,
                        params={
                            "query": query,
                            "tags": tag,
                            "numericFilters": f"created_at_i>{cutoff}",
                            "hitsPerPage": min(per_query, 100),
                        },
                    )
                except Exception as exc:  # one bad query must not kill the run
                    log.warning("hn.query_failed", query=query, tag=tag, error=str(exc))
                    continue

                for hit in payload.get("hits", []):
                    doc = self._to_document(hit)
                    if doc is None or doc.external_id in seen:
                        continue
                    seen.add(doc.external_id)
                    emitted += 1
                    yield doc
                    if emitted >= limit:
                        return

    def _to_document(self, hit: dict[str, Any]) -> RawDocument | None:
        object_id = hit.get("objectID")
        created = hit.get("created_at_i")
        if not object_id or not created:
            return None

        # Stories carry `title` + optional `story_text`/`url`; comments carry
        # `comment_text` and the parent story's title.
        title = hit.get("title") or hit.get("story_title")
        content = hit.get("comment_text") or hit.get("story_text") or ""
        if not content and not title:
            return None

        return RawDocument(
            source=self.name,
            external_id=str(object_id),
            published_at=datetime.fromtimestamp(created, tz=UTC),
            title=title,
            content=strip_html(content),
            url=f"https://news.ycombinator.com/item?id={object_id}",
            author=hit.get("author"),
            score=hit.get("points"),
            comment_count=hit.get("num_comments"),
            raw={"tags": hit.get("_tags", []), "story_url": hit.get("url")},
        )


