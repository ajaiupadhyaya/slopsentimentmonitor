"""REST endpoints.

Every window is expressed in hours and defaults to a trailing week, so a caller
never has to construct dates. Responses carry their own denominators — a
sentiment figure is meaningless without the mention count behind it.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pulseai import analytics
from pulseai.db import get_session
from pulseai.models import Model

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
#: 1 hour to 90 days. Bounded so a stray `hours=10000000` cannot table-scan.
Hours = Annotated[int, Query(ge=1, le=2160)]


@router.get("/health")
async def health(session: SessionDep) -> dict:
    await session.execute(select(1))
    return {"status": "ok"}


@router.get("/overview")
async def overview(session: SessionDep, hours: Hours = 168) -> dict:
    """Everything the dashboard home page needs, in one round trip."""
    return {
        "summary": await analytics.corpus_summary(session),
        "models": [asdict(stat) for stat in await analytics.model_leaderboard(session, hours)],
        "sources": await analytics.source_breakdown(session, hours),
        "timeseries": await analytics.sentiment_timeseries(session, hours=hours),
        "window_hours": hours,
    }


@router.get("/models")
async def list_models(session: SessionDep, hours: Hours = 168) -> dict:
    stats = await analytics.model_leaderboard(session, hours)
    return {"models": [asdict(stat) for stat in stats], "window_hours": hours}


@router.get("/models/{slug}")
async def model_detail(
    slug: str,
    session: SessionDep,
    hours: Hours = 168,
    bucket_hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> dict:
    exists = await session.execute(select(Model.id).where(Model.slug == slug))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"unknown model: {slug}")

    stats = await analytics.model_leaderboard(session, hours, limit=200)
    stat = next((s for s in stats if s.slug == slug), None)

    return {
        "model": asdict(stat) if stat else {"slug": slug, "mentions": 0},
        "timeseries": await analytics.sentiment_timeseries(session, slug, hours, bucket_hours),
        "praise": await analytics.model_documents(session, slug, hours, polarity="positive"),
        "complaints": await analytics.model_documents(session, slug, hours, polarity="negative"),
        "recent": await analytics.model_documents(session, slug, hours, polarity="all"),
        "window_hours": hours,
    }


@router.get("/sentiment")
async def sentiment(
    session: SessionDep,
    slug: str | None = None,
    hours: Hours = 168,
    bucket_hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> dict:
    return {
        "slug": slug,
        "series": await analytics.sentiment_timeseries(session, slug, hours, bucket_hours),
        "window_hours": hours,
    }


@router.get("/mentions")
async def mentions(
    session: SessionDep,
    slug: str,
    hours: Hours = 168,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    polarity: Annotated[str, Query(pattern="^(all|positive|negative)$")] = "all",
) -> dict:
    return {
        "slug": slug,
        "documents": await analytics.model_documents(session, slug, hours, limit, polarity),
    }


@router.get("/compare")
async def compare(
    session: SessionDep,
    slugs: Annotated[str, Query(description="Comma-separated model slugs")],
    hours: Hours = 168,
) -> dict:
    wanted = [s.strip() for s in slugs.split(",") if s.strip()][:6]
    if not wanted:
        raise HTTPException(status_code=400, detail="provide at least one slug")

    return {
        "models": await analytics.compare_models(session, wanted, hours),
        "series": {
            slug: await analytics.sentiment_timeseries(session, slug, hours)
            for slug in wanted
        },
        "window_hours": hours,
    }


@router.get("/sources")
async def sources(session: SessionDep, hours: Hours = 168) -> dict:
    return {"sources": await analytics.source_breakdown(session, hours)}
