"""GitHub issues, pull requests, and discussions mentioning tracked models.

This is where developer sentiment shows up as concrete complaints rather than
opinion — bug reports, migration PRs, "switching away from X" issues.

Auth is optional but strongly advised: 10 search requests/minute unauthenticated
versus 30/minute with a token. `make env` lifts one from the local `gh` login.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from dateutil import parser as dateparser

from pulseai.collectors.base import HttpCollector, RawDocument

log = structlog.get_logger(__name__)

API = "https://api.github.com"

QUERIES: tuple[str, ...] = (
    '"claude code"', '"chatgpt"', '"gpt-5"', '"anthropic api"', '"openai api"',
    '"gemini api"', '"deepseek"', '"ollama"', '"llama.cpp"', '"vllm"', '"copilot"',
)


class GitHubCollector(HttpCollector):
    name = "github"
    type = "code"

    #: GitHub's search endpoint is far more aggressively limited than the REST
    #: API. Pacing here is cheaper than eating 403s and backing off.
    _SEARCH_INTERVAL_SECONDS = 2.5

    def __init__(self, *args: Any, since_hours: int = 72, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.since_hours = since_hours

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        return headers

    def available(self) -> tuple[bool, str]:
        if not self.settings.github_token:
            return True, "no token: limited to 10 search requests/minute"
        return True, ""

    async def collect(self, limit: int = 300) -> AsyncIterator[RawDocument]:
        since = (datetime.now(UTC) - timedelta(hours=self.since_hours)).date().isoformat()
        per_query = max(5, limit // len(QUERIES))
        seen: set[str] = set()
        emitted = 0

        for index, term in enumerate(QUERIES):
            if emitted >= limit:
                return
            if index:
                await asyncio.sleep(self._SEARCH_INTERVAL_SECONDS)

            try:
                payload = await self.get_json(
                    f"{API}/search/issues",
                    params={
                        "q": f"{term} created:>{since}",
                        "sort": "created",
                        "order": "desc",
                        "per_page": min(per_query, 100),
                    },
                    headers=self._headers(),
                )
            except Exception as exc:
                log.warning("github.query_failed", query=term, error=str(exc))
                continue

            for item in payload.get("items", []):
                doc = self._to_document(item)
                if doc is None or doc.external_id in seen:
                    continue
                seen.add(doc.external_id)
                emitted += 1
                yield doc
                if emitted >= limit:
                    return

    def _to_document(self, item: dict[str, Any]) -> RawDocument | None:
        node_id = item.get("node_id") or item.get("id")
        created = item.get("created_at")
        if not node_id or not created:
            return None

        repo = ""
        if url := item.get("repository_url"):
            repo = "/".join(url.rstrip("/").split("/")[-2:])

        return RawDocument(
            source=self.name,
            external_id=str(node_id),
            published_at=dateparser.isoparse(created),
            title=item.get("title"),
            content=(item.get("body") or "")[:20000],
            url=item.get("html_url"),
            author=(item.get("user") or {}).get("login"),
            score=item.get("reactions", {}).get("total_count"),
            comment_count=item.get("comments"),
            raw={
                "repo": repo,
                "state": item.get("state"),
                "is_pull_request": "pull_request" in item,
                "labels": [label.get("name") for label in item.get("labels", [])],
            },
        )
