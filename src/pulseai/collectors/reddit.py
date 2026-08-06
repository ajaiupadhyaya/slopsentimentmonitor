"""Reddit via OAuth.

Reddit's public `.json` endpoints now return an HTML interstitial rather than
data, so OAuth is mandatory. This collector is written and tested but stays
dormant until credentials exist — `available()` reports why, and the ingest run
records it as a skip rather than a failure.

To activate: create a free "script" app at https://www.reddit.com/prefs/apps and
set PULSEAI_REDDIT_CLIENT_ID / PULSEAI_REDDIT_CLIENT_SECRET.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from pulseai.collectors.base import HttpCollector, RawDocument

log = structlog.get_logger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"

SUBREDDITS: tuple[str, ...] = (
    "ChatGPT", "OpenAI", "ClaudeAI", "Anthropic", "GeminiAI", "LocalLLaMA",
    "MachineLearning", "singularity", "artificial", "PromptEngineering",
    "LLM", "grok", "StableDiffusion", "programming", "Python", "ExperiencedDevs",
)


class RedditCollector(HttpCollector):
    name = "reddit"
    type = "forum"

    #: Reddit asks for one request per second from script apps.
    _REQUEST_INTERVAL_SECONDS = 1.1

    def __init__(self, *args: Any, subreddits: tuple[str, ...] | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.subreddits = subreddits or SUBREDDITS
        self._token: str | None = None

    def available(self) -> tuple[bool, str]:
        if not self.settings.reddit_enabled:
            return False, (
                "no credentials: set PULSEAI_REDDIT_CLIENT_ID and "
                "PULSEAI_REDDIT_CLIENT_SECRET (free script app at reddit.com/prefs/apps)"
            )
        return True, ""

    async def _authenticate(self) -> str:
        """Client-credentials grant: read-only access to public listings."""
        if self._token:
            return self._token

        response = await self.client.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=httpx.BasicAuth(
                self.settings.reddit_client_id or "",
                self.settings.reddit_client_secret or "",
            ),
            headers={"User-Agent": self.settings.user_agent},
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("Reddit returned no access_token")
        self._token = token
        return token

    async def collect(self, limit: int = 500) -> AsyncIterator[RawDocument]:
        ok, reason = self.available()
        if not ok:
            log.info("reddit.skipped", reason=reason)
            return

        token = await self._authenticate()
        headers = {"Authorization": f"Bearer {token}", "User-Agent": self.settings.user_agent}
        per_sub = max(5, limit // len(self.subreddits))
        emitted = 0

        for index, subreddit in enumerate(self.subreddits):
            if emitted >= limit:
                return
            if index:
                await asyncio.sleep(self._REQUEST_INTERVAL_SECONDS)

            try:
                payload = await self.get_json(
                    f"{API}/r/{subreddit}/new",
                    params={"limit": min(per_sub, 100)},
                    headers=headers,
                )
            except Exception as exc:
                log.warning("reddit.fetch_failed", subreddit=subreddit, error=str(exc))
                continue

            for child in payload.get("data", {}).get("children", []):
                doc = self._to_document(subreddit, child.get("data", {}))
                if doc is None:
                    continue
                emitted += 1
                yield doc
                if emitted >= limit:
                    return

    def _to_document(self, subreddit: str, data: dict[str, Any]) -> RawDocument | None:
        name = data.get("name")
        created = data.get("created_utc")
        if not name or created is None:
            return None

        return RawDocument(
            source=self.name,
            external_id=str(name),
            published_at=datetime.fromtimestamp(float(created), tz=UTC),
            title=data.get("title"),
            content=(data.get("selftext") or "")[:20000],
            url=f"https://reddit.com{data.get('permalink', '')}",
            author=data.get("author"),
            score=data.get("score"),
            likes=data.get("ups"),
            comment_count=data.get("num_comments"),
            raw={
                "subreddit": subreddit,
                "flair": data.get("link_flair_text"),
                "upvote_ratio": data.get("upvote_ratio"),
                "over_18": data.get("over_18"),
            },
        )
