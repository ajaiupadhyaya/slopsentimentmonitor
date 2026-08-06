"""Sync the static catalog into the database.

The README requires new models be addable without a deploy, so the database is
the runtime source of truth and `registry.py` is only a bootstrap. Re-running
this updates names and aliases in place; it never deletes, because a model row
may already have mentions hanging off it.
"""

from __future__ import annotations

from dataclasses import asdict

import structlog
from sqlalchemy import select

from pulseai.collectors.github import GitHubCollector
from pulseai.collectors.hackernews import HackerNewsCollector
from pulseai.collectors.reddit import RedditCollector
from pulseai.collectors.rss import RSSCollector
from pulseai.db import session_scope
from pulseai.models import Model, Source
from pulseai.registry import MODELS

log = structlog.get_logger(__name__)

SOURCE_SPECS: tuple[tuple[str, str, int], ...] = (
    (HackerNewsCollector.name, HackerNewsCollector.type, 10),
    (RedditCollector.name, RedditCollector.type, 20),
    (GitHubCollector.name, GitHubCollector.type, 30),
    (RSSCollector.name, RSSCollector.type, 40),
)


async def seed_all() -> dict[str, int]:
    """Idempotently insert models and sources. Returns counts of new rows."""
    created = {"models": 0, "sources": 0}

    async with session_scope() as session:
        existing_models = {
            row.slug: row for row in (await session.execute(select(Model))).scalars()
        }
        for spec in MODELS:
            aliases = [asdict(alias) for alias in spec.all_aliases()]
            if row := existing_models.get(spec.slug):
                row.name = spec.name
                row.company = spec.company
                row.website = spec.website
                row.aliases = aliases
            else:
                session.add(
                    Model(
                        slug=spec.slug,
                        name=spec.name,
                        company=spec.company,
                        website=spec.website,
                        aliases=aliases,
                        active=True,
                    )
                )
                created["models"] += 1

        existing_sources = {
            row.name for row in (await session.execute(select(Source))).scalars()
        }
        for name, type_, priority in SOURCE_SPECS:
            if name in existing_sources:
                continue
            session.add(Source(name=name, type=type_, priority=priority, enabled=True))
            created["sources"] += 1

    log.info("seed.complete", **created)
    return created
