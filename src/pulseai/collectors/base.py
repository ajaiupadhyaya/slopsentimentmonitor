"""Collector contract and shared HTTP behaviour.

Collectors know nothing about the database. They fetch, and they yield
`RawDocument`s. That boundary is what lets every collector be tested against
recorded fixtures without Postgres running.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import httpx
import structlog

from pulseai.config import Settings, get_settings

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class RawDocument:
    """Source-agnostic document, pre-normalisation.

    `external_id` must be stable across re-fetches — it is half of the natural
    key that makes ingestion idempotent.
    """

    source: str
    external_id: str
    published_at: datetime
    title: str | None = None
    content: str = ""
    url: str | None = None
    author: str | None = None
    score: int | None = None
    views: int | None = None
    likes: int | None = None
    shares: int | None = None
    comment_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class Collector(Protocol):
    """Every source adapter implements this."""

    name: str
    type: str

    def available(self) -> tuple[bool, str]:
        """Whether this collector can run, and why not if it cannot.

        Reported rather than raised, so a missing Reddit credential shows up as
        a skip in the ingest summary instead of a crash.
        """
        ...

    def collect(self, limit: int) -> AsyncIterator[RawDocument]: ...


class HttpCollector:
    """Base class supplying a retrying HTTP client.

    Retries 429 and 5xx with exponential backoff plus jitter; fails fast on
    other 4xx, because retrying a 404 or a bad token never helps.
    """

    name: str = "http"
    type: str = "http"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.http_timeout_seconds,
                headers={"User-Agent": self.settings.user_agent},
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(f"{type(self).__name__} used outside its async context manager")
        return self._client

    def available(self) -> tuple[bool, str]:
        return True, ""

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self._request("GET", url, **kwargs)
        return response.json()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        response = await self._request("GET", url, **kwargs)
        return response.text

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.settings.http_max_retries):
            try:
                response = await self.client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                last_error = exc
                await self._backoff(attempt)
                continue

            if response.status_code < 400:
                return response

            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable:
                response.raise_for_status()

            last_error = httpx.HTTPStatusError(
                f"{response.status_code} from {url}", request=response.request, response=response
            )
            log.warning(
                "collector.retry",
                source=self.name,
                status=response.status_code,
                attempt=attempt + 1,
            )
            await self._backoff(attempt, response)

        assert last_error is not None
        raise last_error

    async def _backoff(self, attempt: int, response: httpx.Response | None = None) -> None:
        factor = self.settings.http_backoff_factor
        if factor <= 0:
            return

        if response is not None and (header := response.headers.get("Retry-After")):
            try:
                await asyncio.sleep(min(float(header), 30.0) * factor)
                return
            except ValueError:
                pass
        # Jitter matters: several collectors hit rate limits at the same instant
        # and would otherwise retry in lockstep forever.
        await asyncio.sleep(min(2**attempt, 8) * (0.5 + random.random()) * factor)
